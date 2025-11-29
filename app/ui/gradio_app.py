"""Gradio UI for Medical MCQ Generator.
Backend-integrated version."""

import gradio as gr
import logging
from typing import Optional, Tuple, List, Dict, Union, Any
from dataclasses import dataclass, field
import json
import asyncio
import os
import math
import time
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.services.pubmed_service import search_pubmed as pubmed_search_service
from app.services.ingestion_service import register_pdf_source, register_pubmed_source
from app.services.kb_service import (
    get_approved_triplets,
    get_triplet_by_id,
    update_triplet_status,
    upsert_triplet,
)
from app.db.database import SessionLocal, init_db
from app.db.models import Source, Triplet, MCQRecord, PendingSource
from app.core.runner import runner, create_new_session, get_last_session, run_agent
from app.core.llm_manager import llm_manager
from app.services.gemini_image_service import (
    generate_image_from_prompt,
    DEFAULT_IMAGE_SIZE as DEFAULT_IMAGE_DIMENSION,
)
from app.services.gemini_mcq_service import (
    generate_mcq_with_triplets,
    regenerate_mcq_with_feedback,
    regenerate_mcq_with_loop_refinement,
)
from app.services.media_service import (
    save_image,
    get_image_path,
    load_image_bytes,
    delete_image,
)
from sqlalchemy.orm import Session
from sqlalchemy import String


def handle_pending_navigation(direction: int, current_page: int) -> Tuple[str, int, str]:
    new_page = max(1, current_page + direction)
    return render_pending_sources(new_page)


def handle_pending_clear() -> Tuple[str, int, str]:
    _clear_pending_sources()
    return render_pending_sources(1)


def refresh_pending_default() -> Tuple[str, int, str]:
    return render_pending_sources(1)


def load_pending_articles_dropdown() -> Tuple[gr.Dropdown, str]:
    """Load dropdown choices for pending articles."""
    db = SessionLocal()
    try:
        entries = (
            db.query(Source, PendingSource)
            .join(PendingSource, PendingSource.source_id == Source.id)
            .order_by(PendingSource.created_at.desc())
            .all()
        )
        if not entries:
            return (
                gr.update(choices=[], value=None, visible=True, interactive=False),
                "*No pending articles available.*",
            )

        choices = []
        for source, _ in entries:
            year = source.publication_year or "Year N/A"
            title = source.title or "Untitled"
            identifier = source.source_id
            
            # For PDF chunks, show parent PDF name and section
            if source.source_type == "pdf_chunk" and source.parent_source_id:
                parent = db.query(Source).filter(Source.id == source.parent_source_id).first()
                if parent:
                    section_info = f" [{source.section_title}]" if source.section_title else ""
                    title = f"{parent.title}{section_info}"
            
            choices.append(f"{source.id} | {identifier} | {title} ({year})")

        return (
            gr.update(
                choices=choices,
                value=choices[0] if choices else None,
                visible=True,
                interactive=True,
            ),
            f"{len(choices)} pending article(s) loaded.",
        )
    finally:
        db.close()


def _format_triplets_markdown(triplets: List[Dict[str, Any]]) -> str:
    if not triplets:
        return "*No supporting triplets returned.*"
    lines = ["### Supporting Triplets (SNOMED-CT aligned)"]
    for idx, triplet in enumerate(triplets, 1):
        subject = triplet.get("subject", "Unknown")
        action = triplet.get("action", "relates to")
        obj = triplet.get("object", "Unknown")
        relation = triplet.get("relation", "")
        lines.append(f"{idx}. {subject} → {action} → {obj} ({relation})")
    return "\n".join(lines)


def _format_mcq_preview_from_dict(mcq_draft: Dict[str, Any], source: Source) -> str:
    if not mcq_draft:
        return "*No MCQ draft available.*"

    options = mcq_draft.get("options", [])
    options_text = ""
    for idx, option in enumerate(options, 1):
        marker = "(Correct) " if idx - 1 == mcq_draft.get("correct_option", 0) else ""
        options_text += f"{marker}{chr(64+idx)}) {option}\n"

    year = source.publication_year or "Year N/A"
    html = f"""
## Draft MCQ (Not Yet Stored)
**Source:** {source.title or 'Untitled'} ({year}) — {source.source_id}

### Clinical Stem:
{mcq_draft.get('stem', '')}

### Question:
{mcq_draft.get('question', '')}

### Options:
{options_text}
"""
    return html


def _source_to_article_payload(source: Source) -> Dict[str, Any]:
    return {
        "source_id": source.source_id,
        "title": source.title or source.source_id,
        "content": source.content or "",
    }
# Initialize database
init_db()

logger = logging.getLogger(__name__)

# Session management
DEFAULT_USER_ID = "default"
current_session_id = None

# In-memory cache for MCQ drafts keyed by source_id
pending_mcq_cache: Dict[int, Dict[str, Any]] = {}


async def get_or_create_session() -> str:
    """Get or create a session for the current user"""
    global current_session_id
    if not current_session_id:
        session_id = await get_last_session(DEFAULT_USER_ID)
        if not session_id:
            current_session_id = await create_new_session(DEFAULT_USER_ID)
        else:
            current_session_id = session_id
    return current_session_id


@dataclass
class TripletAutoProcessResult:
    """Aggregator for auto triplet processing outcomes."""

    accepted: List[Triplet] = field(default_factory=list)
    pending: List[Triplet] = field(default_factory=list)
    skipped_duplicates: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.accepted) + len(self.pending) + self.skipped_duplicates

    def summary(self) -> str:
        parts = []
        if self.accepted:
            parts.append(f"{len(self.accepted)} accepted")
        if self.pending:
            parts.append(f"{len(self.pending)} pending review")
        if self.skipped_duplicates:
            parts.append(f"{self.skipped_duplicates} duplicates skipped")
        if not parts:
            return "No triplets extracted."
        return ", ".join(parts)


def _normalize_context_sentences(value: Any) -> List[str]:
    """Ensure context sentences are stored as a list of strings."""
    if not value:
        return []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, list):
                return [str(item).strip() for item in decoded if str(item).strip()]
        except json.JSONDecodeError:
            return [value.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _persist_fallback_payload(
    db: Session,
    source: Source,
    payload: Dict[str, Any],
) -> Optional[Tuple[Triplet, MCQRecord]]:
    """Deprecated - fallback payloads stored via pending MCQ cache."""
    return None


def _ensure_pending_source(db: Session, source: Source) -> None:
    """Add source to pending review queue if not already present."""
    existing = db.query(PendingSource).filter(PendingSource.source_id == source.id).first()
    if not existing:
        db.add(PendingSource(source_id=source.id))
        db.commit()


def _list_pending_sources(page: int = 1, page_size: int = 6) -> Tuple[List[Tuple[Source, PendingSource]], int]:
    """Return paginated pending sources and total pages."""
    db = SessionLocal()
    try:
        total = db.query(PendingSource).count()
        total_pages = max(1, math.ceil(total / page_size)) if total else 1
        page = max(1, min(page, total_pages))
        entries = (
            db.query(Source, PendingSource)
            .join(PendingSource, PendingSource.source_id == Source.id)
            .order_by(PendingSource.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return entries, total_pages
    finally:
        db.close()


def _remove_pending_source(source_id: int) -> None:
    db = SessionLocal()
    try:
        db.query(PendingSource).filter(PendingSource.source_id == source_id).delete()
        db.commit()
    finally:
        db.close()


def _clear_pending_sources() -> None:
    db = SessionLocal()
    try:
        db.query(PendingSource).delete()
        db.commit()
    finally:
        db.close()


def render_pending_sources(page: int = 1, page_size: int = 6) -> Tuple[str, int, str]:
    """Render markdown for pending sources with pagination info."""
    entries, total_pages = _list_pending_sources(page, page_size)
    if not entries:
        return "*No articles pending review.*", 1, "Page 1/1"

    html_lines = ["### Pending Review"]
    for source, pending in entries:
        year = source.publication_year or "Year N/A"
        label = source.source_id
        
        # Show section info for PDF chunks
        section_info = ""
        if source.source_type == "pdf_chunk" and source.section_title:
            section_info = f"\n- Section: {source.section_title}"
            # Get parent PDF name if available
            if source.parent_source_id:
                db = SessionLocal()
                try:
                    parent = db.query(Source).filter(Source.id == source.parent_source_id).first()
                    if parent:
                        label = f"{parent.title} - {source.section_title}"
                finally:
                    db.close()
        
        html_lines.append(
            f"**{source.title or 'Untitled'}**\n"
            f"- Year: {year}\n"
            f"- Identifier: {label}{section_info}\n"
            f"- Added: {pending.created_at}\n"
        )
    info = f"Page {page}/{total_pages}"
    return "\n".join(html_lines), page, info


def _store_triplets_with_auto_accept(
    db: Session,
    source: Source,
    extracted_triplets: List[Dict[str, Any]],
) -> TripletAutoProcessResult:
    """Persist extracted triplets with duplicate checks and auto-accept logic."""
    result = TripletAutoProcessResult()

    for triplet_data in extracted_triplets or []:
        subject = (triplet_data.get("subject") or "").strip()
        action = (triplet_data.get("action") or "").strip()
        obj = (triplet_data.get("object") or "").strip()
        relation = (triplet_data.get("relation") or "").strip()

        if not all([subject, action, obj, relation]):
            result.errors.append("Incomplete triplet fields encountered.")
            continue

        duplicate = db.query(Triplet).filter(
            Triplet.subject == subject,
            Triplet.action == action,
            Triplet.object == obj,
            Triplet.relation == relation,
            Triplet.source_id == source.id,
        ).first()
        if duplicate:
            result.skipped_duplicates += 1
            continue

        accepted_match = db.query(Triplet).filter(
            Triplet.subject == subject,
            Triplet.action == action,
            Triplet.object == obj,
            Triplet.relation == relation,
            Triplet.status == "accepted",
        ).first()

        schema_valid = bool(triplet_data.get("schema_valid"))
        status = "accepted" if schema_valid or accepted_match else "pending"

        triplet = upsert_triplet(
            db=db,
            subject=subject,
            action=action,
            object=obj,
            relation=relation,
            source_id=source.id,
            context_sentences=_normalize_context_sentences(triplet_data.get("context_sentences")),
            schema_valid=schema_valid,
            status=status,
        )

        if status == "accepted":
            result.accepted.append(triplet)
        else:
            result.pending.append(triplet)

    return result


def _build_mcq_prompt(triplet: Triplet, source: Source) -> str:
    """Create a deterministic instruction payload for MCQ generation."""
    context_sentences = []
    if triplet.context_sentences:
        try:
            context_sentences = json.loads(triplet.context_sentences)
        except json.JSONDecodeError:
            context_sentences = [triplet.context_sentences]
    context_block = "\n".join(f"- {sentence}" for sentence in context_sentences)

    return (
        "Use the MCQGenerationAgent within the pipeline to create a single clinical MCQ.\n"
        "Instructions:\n"
        "1. Derive the MCQ from the provided triplet and context sentences.\n"
        "2. Return JSON with keys: mcq_draft (stem, question, options[5], correct_option,"
        " visual_kernel_draft) and visual_payload (optimized_visual_prompt, visual_triplet).\n"
        "3. Keep provenance aligned with the provided source details.\n\n"
        f"Triplet:\nSubject: {triplet.subject}\nAction: {triplet.action}\n"
        f"Object: {triplet.object}\nRelation: {triplet.relation}\n"
        f"Source Title: {source.title}\nSource ID: {source.source_id}\n"
        "Context Sentences:\n"
        f"{context_block if context_block else '- None provided'}"
    )


async def _auto_generate_mcqs_for_triplets(
    db: Session,
    triplets: List[Triplet],
    source: Source,
    session_id: str,
    model_id: str,
) -> Tuple[int, List[int]]:
    """Automatically generate MCQs for accepted triplets."""
    generated = 0
    mcq_ids: List[int] = []

    for triplet in triplets:
        existing_mcq = db.query(MCQRecord).filter(MCQRecord.triplet_id == triplet.id).first()
        if existing_mcq:
            continue

        prompt = _build_mcq_prompt(triplet, source)
        try:
            result = await run_agent(
                new_message=prompt,
                user_id=DEFAULT_USER_ID,
                session_id=session_id,
                model_id=model_id,
            )
        except Exception as exc:
            logger.warning("MCQ generation failed for triplet %s: %s", triplet.id, exc)
            continue

        payload = _coerce_result_to_dict(result)
        mcq_draft = payload.get("mcq_draft") or payload.get("current_mcqs")
        visual_payload = payload.get("visual_payload", {})

        if not isinstance(mcq_draft, dict):
            continue

        options = mcq_draft.get("options") or []
        if len(options) != 5:
            continue

        mcq = MCQRecord(
            stem=mcq_draft.get("stem", ""),
            question=mcq_draft.get("question", ""),
            options=json.dumps(options),
            correct_option=mcq_draft.get("correct_option", 0),
            source_id=source.id,
            triplet_id=triplet.id,
            visual_prompt=visual_payload.get("optimized_visual_prompt"),
            visual_triplet=visual_payload.get("visual_triplet"),
            status="pending",
        )
        db.add(mcq)
        db.commit()
        db.refresh(mcq)

        generated += 1
        mcq_ids.append(mcq.id)

    return generated, mcq_ids


async def _auto_process_source(
    db: Session,
    source: Source,
    model_id: str,
) -> str:
    """Run extraction + auto MCQ workflow for a registered source."""
    session_id = await get_or_create_session()
    try:
        result = await run_agent(
            new_message=f"Process source {source.source_id} through the MCQ pipeline.",
            user_id=DEFAULT_USER_ID,
            session_id=session_id,
            model_id=model_id,
        )
    except Exception as exc:
        return f"Pipeline error for {source.source_id}: {exc}"

    payload = _coerce_result_to_dict(result)
    extracted_triplets = payload.get("extracted_triplets", [])

    triplet_result = _store_triplets_with_auto_accept(db, source, extracted_triplets)
    summary = f"AutoTripletFilter: {triplet_result.summary()}"
    fallback_note = ""

    fallback_payload = payload.get("fallback_payload")
    if fallback_payload:
        fallback_result = _persist_fallback_payload(db, source, fallback_payload)
        if fallback_result:
            fallback_note = " Fallback MCQ stored for this article."
        else:
            fallback_note = " Fallback payload detected but could not be stored."

    if not triplet_result.accepted:
        return f"{summary}. No MCQs generated yet.{fallback_note}"

    mcq_count, _ = await _auto_generate_mcqs_for_triplets(
        db=db,
        triplets=triplet_result.accepted,
        source=source,
        session_id=session_id,
        model_id=model_id,
    )

    if mcq_count == 0:
        return f"{summary}. MCQ generation deferred (see MCQ tab for manual actions).{fallback_note}"

    return f"{summary}. Auto-generated {mcq_count} MCQs.{fallback_note}"


# ========== Source Search/Upload Handlers ==========

def handle_pubmed_search(keywords: str) -> Tuple[List[Dict], str]:
    """Search PubMed and return article list plus status message."""
    if not keywords.strip():
        return [], "Please enter search keywords."
    
    try:
        articles = pubmed_search_service(keywords, max_results=10)
        if not articles:
            return [], f"No articles found for '{keywords}'."
        return articles, f"Found {len(articles)} articles for '{keywords}'."
    except Exception as e:
        return [], f"Error searching PubMed: {e}"


def format_articles_markdown(articles: List[Dict]) -> str:
    if not articles:
        return "No articles found. Try different keywords."
    lines = ["Search results:"]
    for idx, article in enumerate(articles, 1):
        year = article.get("year") or "Year N/A"
        lines.append(
            f"**{idx}. {article['title']}**\n"
            f"- Year: {year}\n"
            f"- PubMed ID: {article['pubmed_id']}\n"
        )
    return "\n".join(lines)


async def _process_article_selection(article: Dict, model_id: str) -> str:
    """Shared ingestion logic for a PubMed article dict."""
    db = SessionLocal()
    try:
        source_dict = register_pubmed_source(article, db)
        source = db.query(Source).filter(Source.id == source_dict["id"]).first()
        if not source:
            return "Source registration failed."

        _ensure_pending_source(db, source)
        pending_mcq_cache.pop(source.id, None)
        return f"Article queued for MCQ review: {source.title or source.source_id}"
    finally:
        db.close()


async def handle_article_selection_from_input(
    selection_input: str,
    articles_state: List[Dict],
    model_id: str,
) -> str:
    """Select one or more articles using comma-separated indices."""
    if not articles_state:
        return "No search results available. Run a search first."
    
    if not selection_input.strip():
        return "Enter an article number (e.g., 1) or multiple numbers separated by commas (e.g., 1,3,5)."
    
    indices = []
    warnings = []
    for token in selection_input.split(","):
        token = token.strip()
        if not token:
            continue
        if not token.isdigit():
            warnings.append(f"'{token}' is not a number.")
            continue
        idx = int(token)
        if idx < 1 or idx > len(articles_state):
            warnings.append(f"Article {idx} is out of range.")
        else:
            indices.append(idx - 1)
    
    if not indices:
        return "No valid article numbers provided." + (" " + " ".join(warnings) if warnings else "")
    
    messages = []
    for idx in sorted(set(indices)):
        article = articles_state[idx]
        try:
            msg = await _process_article_selection(article, model_id)
            messages.append(f"[{idx + 1}] {msg}")
        except Exception as e:
            messages.append(f"[{idx + 1}] Error selecting article: {e}")
    
    if warnings:
        messages.append("Warnings: " + " ".join(warnings))
    return "\n".join(messages)


def _coerce_result_to_dict(result: object) -> Dict:
    """Accept both dict and streaming Event outputs from ADK."""
    if isinstance(result, dict):
        return result
    content = getattr(result, "content", None)
    if content and getattr(content, "parts", None):
        texts = []
        for part in content.parts:
            text_value = getattr(part, "text", None)
            if text_value:
                texts.append(text_value)
        if texts:
            joined = "\n".join(texts).strip()
            try:
                return json.loads(joined)
            except json.JSONDecodeError:
                return {"raw_text": joined}
    return {}


def handle_pdf_upload(file, model_id: str) -> str:
    """Handle PDF upload and trigger extraction"""
    if file is None:
        return "No file uploaded."
    
    try:
        # Read PDF bytes
        with open(file.name, 'rb') as f:
            pdf_bytes = f.read()
        
        # Register PDF source (creates parent + chunks)
        db = SessionLocal()
        try:
            source_dict = register_pdf_source(file.name, pdf_bytes, db)
            parent_source = db.query(Source).filter(Source.id == source_dict["id"]).first()
            if not parent_source:
                return "Failed to register PDF source."

            # Add all chunk sources to pending queue (not the parent)
            chunk_sources = db.query(Source).filter(
                Source.parent_source_id == parent_source.id
            ).all()
            
            chunks_added = 0
            for chunk_source in chunk_sources:
                _ensure_pending_source(db, chunk_source)
                pending_mcq_cache.pop(chunk_source.id, None)
                chunks_added += 1
            
            if chunks_added > 0:
                return f"PDF processed: {chunks_added} section(s) queued for MCQ review from '{parent_source.title or parent_source.source_id}'"
            else:
                return f"PDF processed but no sections found: {parent_source.title or parent_source.source_id}"
        finally:
            db.close()
    except Exception as e:
        return f"Error processing PDF: {e}"


def refresh_ingested_sources() -> str:
    """Refresh and display selected sources"""
    db = SessionLocal()
    try:
        sources = db.query(Source).order_by(Source.created_at.desc()).limit(10).all()
        
        if not sources:
            return "*No sources selected yet*"
        
        html = "### Selected Sources\n\n"
        for source in sources:
            source_type_label = "PubMed" if source.source_type == "pubmed" else "Upload"
            total_triplets = db.query(Triplet).filter(Triplet.source_id == source.id).count()
            accepted_triplets = db.query(Triplet).filter(
                Triplet.source_id == source.id,
                Triplet.status == "accepted"
            ).count()
            mcq_count = db.query(MCQRecord).filter(MCQRecord.source_id == source.id).count()
            html += f"""
**{source.title[:60]}...**
- Type: {source_type_label}
- ID: {source.source_id}
- Triplets: {accepted_triplets}/{total_triplets} accepted
- MCQs: {mcq_count} generated
---
"""
        return html
    finally:
        db.close()


# ========== MCQ Review Handlers ==========

def _parse_source_choice(choice: str) -> Optional[int]:
    if not choice:
        return None
    return int(choice.split("|", 1)[0].strip())


def _parse_mcq_choice(choice: str) -> Optional[int]:
    if not choice:
        return None
    return int(choice.split("|", 1)[0].strip())


def load_articles_for_mcq_dropdown() -> Tuple[gr.Dropdown, str]:
    """Load recent articles for MCQ review dropdown."""
    db = SessionLocal()
    try:
        sources = db.query(Source).order_by(Source.created_at.desc()).limit(20).all()
        choices = [
            f"{source.id} | {source.title or 'Untitled Source'}"
            for source in sources
        ]
        if not choices:
            return gr.update(choices=[], value=None, visible=False), "*No articles available yet.*"
        return (
            gr.update(choices=choices, value=choices[0], visible=True),
            f"Loaded {len(choices)} recent articles.",
        )
    finally:
        db.close()


def load_mcqs_for_article_dropdown(source_choice: str) -> Tuple[str, gr.Dropdown]:
    """Populate MCQ dropdown for a selected article."""
    source_id = _parse_source_choice(source_choice)
    if not source_id:
        return "Select an article first.", gr.update(choices=[], value=None, visible=False)

    db = SessionLocal()
    try:
        mcqs = (
            db.query(MCQRecord)
            .filter(MCQRecord.source_id == source_id)
            .order_by(MCQRecord.created_at.desc())
            .all()
        )
        if not mcqs:
            return (
                "No MCQs stored for this article yet.",
                gr.update(choices=[], value=None, visible=False),
            )

        choices = [
            f"{mcq.id} | MCQ {idx + 1}: {mcq.question[:60]}"
            for idx, mcq in enumerate(mcqs)
        ]
        return (
            f"Found {len(mcqs)} MCQs for this article.",
            gr.update(choices=choices, value=choices[0], visible=True),
        )
    finally:
        db.close()


def handle_view_mcq(mcq_choice: str) -> Tuple[str, str, str, Optional[int]]:
    """Display stored MCQ without regenerating."""
    mcq_id = _parse_mcq_choice(mcq_choice)
    if not mcq_id:
        return "*Select an MCQ first*", "", "", None

    db = SessionLocal()
    try:
        mcq = db.query(MCQRecord).filter(MCQRecord.id == mcq_id).first()
        if not mcq:
            return "MCQ not found.", "", "", None
        source = db.query(Source).filter(Source.id == mcq.source_id).first()
        triplet = db.query(Triplet).filter(Triplet.id == mcq.triplet_id).first()
        html = format_original_mcq(mcq, source, triplet) if source and triplet else "MCQ data incomplete."
        return html, mcq.visual_prompt or "", mcq.visual_triplet or "", mcq.id
    finally:
        db.close()


async def handle_regenerate_mcq(mcq_choice: str, model_id: str) -> Tuple[str, str, str, Optional[int]]:
    """Regenerate MCQ for selected record using its triplet."""
    mcq_id = _parse_mcq_choice(mcq_choice)
    if not mcq_id:
        return "*Select an MCQ first*", "", "", None

    db = SessionLocal()
    try:
        mcq = db.query(MCQRecord).filter(MCQRecord.id == mcq_id).first()
        if not mcq:
            return "MCQ not found.", "", "", None
        triplet = db.query(Triplet).filter(Triplet.id == mcq.triplet_id).first()
        source = db.query(Source).filter(Source.id == mcq.source_id).first()
        if not triplet or not source:
            return "Associated triplet/source not found.", "", "", None

        session_id = await get_or_create_session()
        prompt = _build_mcq_prompt(triplet, source)
        result = await run_agent(
            new_message=prompt,
            user_id=DEFAULT_USER_ID,
            session_id=session_id,
            model_id=model_id,
        )

        payload = _coerce_result_to_dict(result)
        mcq_draft = payload.get("mcq_draft", {})
        visual_payload = payload.get("visual_payload", {})
        if not mcq_draft:
            return "MCQ regeneration failed. Please retry.", "", "", None

        options = mcq_draft.get("options", [])
        if len(options) == 5:
            mcq.options = json.dumps(options)
        mcq.stem = mcq_draft.get("stem", mcq.stem)
        mcq.question = mcq_draft.get("question", mcq.question)
        mcq.correct_option = mcq_draft.get("correct_option", mcq.correct_option)
        mcq.visual_prompt = visual_payload.get("optimized_visual_prompt", mcq.visual_prompt)
        mcq.visual_triplet = visual_payload.get("visual_triplet", mcq.visual_triplet)
        db.commit()
        db.refresh(mcq)

        html = format_original_mcq(mcq, source, triplet)
        return html, mcq.visual_prompt or "", mcq.visual_triplet or "", mcq.id
    finally:
        db.close()


async def handle_generate_mcqs_for_article(source_choice: str, model_id: str) -> str:
    """Trigger MCQ generation for all accepted triplets in an article."""
    source_id = _parse_source_choice(source_choice)
    if not source_id:
        return "Select an article first."

    db = SessionLocal()
    try:
        source = db.query(Source).filter(Source.id == source_id).first()
        if not source:
            return "Article not found."

        accepted_triplets = (
            db.query(Triplet)
            .filter(Triplet.source_id == source.id, Triplet.status == "accepted")
            .all()
        )
        if not accepted_triplets:
            return "No accepted triplets for this article yet."

        session_id = await get_or_create_session()
        mcq_count, _ = await _auto_generate_mcqs_for_triplets(
            db=db,
            triplets=accepted_triplets,
            source=source,
            session_id=session_id,
            model_id=model_id,
        )
        return f"Generated {mcq_count} MCQs for {source.source_id}."
    finally:
        db.close()


def generate_mcq_for_pending_article(source_choice: str, model_id: str) -> Tuple[str, str, str]:
    """Generate MCQ draft for a pending article and cache it in memory."""
    source_id = _parse_source_choice(source_choice)
    if not source_id:
        return "*Select a pending article first.*", "", ""

    db = SessionLocal()
    try:
        source = db.query(Source).filter(Source.id == source_id).first()
        if not source:
            return "Article not found.", "", ""

        article_payload = _source_to_article_payload(source)
        result = generate_mcq_with_triplets(article_payload, model_id=model_id)
        if not result.success or not result.payload:
            return result.message or "MCQ generation failed. Please retry.", "", ""

        payload = result.payload
        mcq_draft = payload.get("mcq") or payload.get("mcq_draft")
        triplets = payload.get("triplets") or []
        visual_prompt = payload.get("visual_prompt") or ""

        if not mcq_draft or not triplets:
            return "MCQ generation failed. Please retry.", "", ""

        visual_payload = {"optimized_visual_prompt": visual_prompt}

        pending_mcq_cache[source_id] = {
            "mcq": mcq_draft,
            "visual": visual_payload,
            "triplets": triplets,
            "timestamp": time.time(),
        }

        mcq_html = _format_mcq_preview_from_dict(mcq_draft, source)
        triplet_md = _format_triplets_markdown(triplets)
        return mcq_html, visual_prompt, triplet_md
    finally:
        db.close()


def apply_mcq_feedback(source_choice: str, feedback: str, model_id: str) -> Tuple[str, str, str]:
    """Regenerate MCQ draft with reviewer feedback using LoopAgent refinement."""
    source_id = _parse_source_choice(source_choice)
    if not source_id:
        return "*Select a pending article first.*", "", ""
    if not feedback.strip():
        return "Provide feedback before requesting an update.", "", ""

    db = SessionLocal()
    try:
        source = db.query(Source).filter(Source.id == source_id).first()
        if not source:
            return "Article not found.", "", ""

        previous_mcq = pending_mcq_cache.get(source_id, {}).get("mcq", {})
        article_payload = _source_to_article_payload(source)
        regen_payload = {
            "mcq": previous_mcq,
            "triplets": pending_mcq_cache.get(source_id, {}).get("triplets", []),
            "visual_prompt": pending_mcq_cache.get(source_id, {}).get("visual", {}).get("optimized_visual_prompt", ""),
        }
        
        # Use LoopAgent refinement (falls back to direct feedback if LoopAgent fails early)
        result = regenerate_mcq_with_loop_refinement(
            article_payload, 
            regen_payload, 
            feedback, 
            model_id=model_id,
            max_iterations=2
        )
        
        if not result.success or not result.payload:
            return result.message or "MCQ regeneration failed. Please retry.", "", ""

        payload = result.payload
        mcq_draft = payload.get("mcq") or payload.get("mcq_draft")
        triplets = payload.get("triplets") or []
        visual_prompt = payload.get("visual_prompt") or ""

        if not mcq_draft or not triplets:
            return "MCQ regeneration failed. Please retry.", "", ""

        visual_payload = {"optimized_visual_prompt": visual_prompt}

        pending_mcq_cache[source_id] = {
            "mcq": mcq_draft,
            "visual": visual_payload,
            "triplets": triplets,
            "timestamp": time.time(),
        }

        mcq_html = _format_mcq_preview_from_dict(mcq_draft, source)
        triplet_md = _format_triplets_markdown(triplets)
        return mcq_html, visual_prompt, triplet_md
    finally:
        db.close()


def handle_accept_mcq(source_choice: str, visual_prompt: str) -> Tuple[str, Optional[int]]:
    """Persist the pending MCQ for a source and remove it from queue."""
    source_id = _parse_source_choice(source_choice)
    if not source_id:
        return "Select a pending article first.", None

    cache_entry = pending_mcq_cache.get(source_id)
    if not cache_entry:
        return "Generate an MCQ before accepting.", None

    db = SessionLocal()
    try:
        source = db.query(Source).filter(Source.id == source_id).first()
        if not source:
            return "Article not found.", None

        mcq_draft = cache_entry.get("mcq", {})
        triplets = cache_entry.get("triplets", [])
        options = mcq_draft.get("options", [])
        if len(options) != 5:
            return "MCQ draft must contain exactly 5 options before acceptance.", None

        # Persist triplets
        primary_triplet_id: Optional[int] = None
        for triplet_data in triplets:
            stored_triplet = upsert_triplet(
                db=db,
                subject=triplet_data.get("subject", "").strip(),
                action=triplet_data.get("action", "").strip(),
                object=triplet_data.get("object", "").strip(),
                relation=triplet_data.get("relation", "INDICATES").strip(),
                source_id=source.id,
                context_sentences=_normalize_context_sentences(triplet_data.get("context_sentences")),
                schema_valid=True,
                status="accepted",
            )
            if primary_triplet_id is None:
                primary_triplet_id = stored_triplet.id

        visual_prompt_text = (visual_prompt or "").strip()
        mcq = MCQRecord(
            stem=mcq_draft.get("stem", ""),
            question=mcq_draft.get("question", ""),
            options=json.dumps(options),
            correct_option=mcq_draft.get("correct_option", 0),
            source_id=source.id,
            triplet_id=primary_triplet_id,
            visual_prompt=visual_prompt_text,
            status="approved",  # Changed from "pending" to "approved" when user accepts
        )
        db.add(mcq)
        
        # Remove pending source in the same transaction
        db.query(PendingSource).filter(PendingSource.source_id == source_id).delete()
        
        db.commit()
        db.refresh(mcq)

        pending_mcq_cache.pop(source_id, None)

        return f"MCQ accepted and stored with ID {mcq.id}.", mcq.id
    finally:
        db.close()


def handle_accept_visual_prompt(mcq_id: Optional[int], visual_prompt: str) -> Tuple[str, str, bool]:
    """Persist the latest visual prompt for the stored MCQ and auto-generate image."""
    if not mcq_id:
        return "Accept the MCQ first.", visual_prompt, False

    prompt_text = visual_prompt.strip()
    db = SessionLocal()
    try:
        mcq = db.query(MCQRecord).filter(MCQRecord.id == mcq_id).first()
        if not mcq:
            return "MCQ not found.", visual_prompt, False

        mcq.visual_prompt = prompt_text
        db.commit()
        return "Visual prompt saved.", prompt_text, True
    finally:
        db.close()


def load_stored_mcq_view(mcq_id: Optional[int]) -> Tuple[str, str, str, bool]:
    """Return formatted displays for the builder once an MCQ is persisted."""
    if not mcq_id:
        return (
            "*Generate an MCQ draft to begin.*",
            "*Triplet details will appear here.*",
            "",
            False,
        )

    db = SessionLocal()
    try:
        record = (
            db.query(MCQRecord, Source, Triplet)
            .join(Source, MCQRecord.source_id == Source.id)
            .outerjoin(Triplet, MCQRecord.triplet_id == Triplet.id)
            .filter(MCQRecord.id == mcq_id)
            .first()
        )
        if not record:
            return (
                "*Stored MCQ could not be found.*",
                "*Triplet details unavailable.*",
                "",
                False,
            )

        mcq, source, triplet = record
        mcq_html = format_original_mcq(mcq, source, triplet) if source else "*Source metadata missing.*"
        if triplet:
            triplet_md = _format_triplets_markdown(
                [
                    {
                        "subject": triplet.subject,
                        "action": triplet.action,
                        "object": triplet.object,
                        "relation": triplet.relation,
                    }
                ]
            )
        else:
            triplet_md = "*No triplet stored for this MCQ.*"

        saved_flag = bool(mcq.visual_prompt)
        return mcq_html, triplet_md, mcq.visual_prompt or "", saved_flag
    finally:
        db.close()


def _visual_prompt_button_state(saved: bool) -> gr.Button:
    """Return a button update reflecting whether the visual prompt is saved."""
    if saved:
        return gr.update(value="Visual Prompt Saved", interactive=False, variant="secondary")
    return gr.update(value="Accept Visual Prompt", interactive=True, variant="primary")


def _list_stored_mcqs(page: int = 1, page_size: int = 10, query: Optional[str] = None) -> Tuple[List[Tuple[MCQRecord, Source, Optional[Triplet]]], int]:
    """Return paginated stored MCQs with optional search."""
    db = SessionLocal()
    try:
        q = (
            db.query(MCQRecord, Source, Triplet)
            .join(Source, MCQRecord.source_id == Source.id)
            .outerjoin(Triplet, MCQRecord.triplet_id == Triplet.id)
        )
        
        if query:
            like_term = f"%{query}%"
            q = q.filter(
                (Source.source_id.ilike(like_term))
                | (Source.title.ilike(like_term))
                | (Source.authors.ilike(like_term))
                | (MCQRecord.question.ilike(like_term))
                | (MCQRecord.stem.ilike(like_term))
                | (Source.publication_year.cast(String).ilike(like_term))
            )
        
        total = q.count()
        total_pages = max(1, math.ceil(total / page_size)) if total else 1
        page = max(1, min(page, total_pages))
        
        results = (
            q.order_by(MCQRecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return results, total_pages
    finally:
        db.close()


def render_kb_list(page: int = 1, query: Optional[str] = None) -> Tuple[str, int, str]:
    """Render Knowledge Base list with pagination (6 per page)."""
    results, total_pages = _list_stored_mcqs(page, 6, query)
    
    if not results:
        return "*No MCQs found.*", 1, "Page 1/1"
    
    lines = ["### Stored MCQs (6 per page)\n"]
    for mcq, source, triplet in results:
        year = source.publication_year or "Year N/A"
        title = source.title or "Untitled"
        question_preview = mcq.question[:80] + "..." if len(mcq.question) > 80 else mcq.question
        lines.append(
            f"**MCQ ID: {mcq.id}** | {title} ({year})\n"
            f"Question: {question_preview}\n"
            "---\n"
        )
    
    info = f"Page {page}/{total_pages} ({len(results)} shown)"
    return "\n".join(lines), page, info


def search_stored_mcqs(query: str) -> Tuple[str, int, str]:
    """Search stored MCQs by various criteria."""
    query = (query or "").strip()
    return render_kb_list(1, query if query else None)


def get_mcq_detail(mcq_id: int) -> Tuple[str, str, Optional[gr.Image], str]:
    """Get detailed view of an MCQ formatted like Tab 2, including triplets, visual prompt, and image."""
    db = SessionLocal()
    try:
        result = (
            db.query(MCQRecord, Source, Triplet)
            .join(Source, MCQRecord.source_id == Source.id)
            .outerjoin(Triplet, MCQRecord.triplet_id == Triplet.id)
            .filter(MCQRecord.id == mcq_id)
            .first()
        )
        
        if not result:
            return "*MCQ not found.*", "", gr.update(visible=False, value=None), ""
        
        mcq, source, triplet = result
        
        # Format MCQ like Tab 2
        mcq_html = format_original_mcq(mcq, source, triplet)
        if mcq.visual_prompt:
            mcq_html += f"\n### Visual Prompt:\n{mcq.visual_prompt}\n"
        
        # Format triplets
        triplet_md = ""
        if triplet:
            context_sentences = _normalize_context_sentences(triplet.context_sentences)
            triplet_md = f"""
### Supporting Triplet (SNOMED-CT aligned)
- **Subject:** {triplet.subject}
- **Action:** {triplet.action}
- **Object:** {triplet.object}
- **Relation:** {triplet.relation}
- **Context Sentences:**
{chr(10).join(f"  - {s}" for s in context_sentences) if context_sentences else "  - None provided"}
"""
        else:
            triplet_md = "*No triplet associated with this MCQ.*"
        
        # Load image if exists
        image_display = gr.update(visible=False, value=None)
        image_status = ""
        if mcq.image_url:
            image_path = get_image_path(mcq_id)
            if image_path and image_path.exists():
                try:
                    image = Image.open(image_path)
                    image_display = gr.update(value=image, visible=True)
                    image_status = f"Image available: {mcq.image_url}"
                except Exception:
                    image_status = f"Image file exists but could not be loaded: {mcq.image_url}"
            else:
                image_status = f"Image path in DB but file not found: {mcq.image_url}"
        else:
            image_status = "No image stored for this MCQ."
        
        return mcq_html, triplet_md, image_display, image_status
    finally:
        db.close()


def export_mcq_json(mcq_id: int) -> str:
    """Export MCQ as JSON."""
    db = SessionLocal()
    try:
        result = (
            db.query(MCQRecord, Source, Triplet)
            .join(Source, MCQRecord.source_id == Source.id)
            .outerjoin(Triplet, MCQRecord.triplet_id == Triplet.id)
            .filter(MCQRecord.id == mcq_id)
            .first()
        )
        
        if not result:
            return "MCQ not found."
        
        mcq, source, triplet = result
        export_data = {
            "mcq_id": mcq.id,
            "source": {
                "id": source.id,
                "source_id": source.source_id,
                "title": source.title,
                "authors": source.authors,
                "year": source.publication_year,
            },
            "stem": mcq.stem,
            "question": mcq.question,
            "options": json.loads(mcq.options),
            "correct_option": mcq.correct_option,
            "visual_prompt": mcq.visual_prompt,
            "status": mcq.status,
            "created_at": mcq.created_at.isoformat() if mcq.created_at else None,
        }
        
        if triplet:
            export_data["triplet"] = {
                "subject": triplet.subject,
                "action": triplet.action,
                "object": triplet.object,
                "relation": triplet.relation,
                "context_sentences": _normalize_context_sentences(triplet.context_sentences),
            }
        
        if mcq.image_url:
            export_data["image_path"] = mcq.image_url
        
        return json.dumps(export_data, indent=2)
    finally:
        db.close()


def export_mcq_text(mcq_id: int) -> str:
    """Export MCQ as plain text."""
    db = SessionLocal()
    try:
        result = (
            db.query(MCQRecord, Source, Triplet)
            .join(Source, MCQRecord.source_id == Source.id)
            .outerjoin(Triplet, MCQRecord.triplet_id == Triplet.id)
            .filter(MCQRecord.id == mcq_id)
            .first()
        )
        
        if not result:
            return "MCQ not found."
        
        mcq, source, triplet = result
        options = json.loads(mcq.options)
        
        lines = [
            f"MCQ ID: {mcq.id}",
            f"Source: {source.title or 'Untitled'} ({source.source_id})",
            f"Authors: {source.authors or 'N/A'}",
            f"Year: {source.publication_year or 'N/A'}",
            "",
            f"Stem: {mcq.stem}",
            "",
            f"Question: {mcq.question}",
            "",
            "Options:",
        ]
        for idx, opt in enumerate(options):
            marker = " [CORRECT]" if idx == mcq.correct_option else ""
            lines.append(f"  {chr(65+idx)}) {opt}{marker}")
        
        if triplet:
            lines.extend([
                "",
                "Triplet:",
                f"  Subject: {triplet.subject}",
                f"  Action: {triplet.action}",
                f"  Object: {triplet.object}",
                f"  Relation: {triplet.relation}",
            ])
        
        if mcq.visual_prompt:
            lines.extend(["", f"Visual Prompt: {mcq.visual_prompt}"])
        
        if mcq.image_url:
            lines.extend(["", f"Image: {mcq.image_url}"])
        
        return "\n".join(lines)
    finally:
        db.close()


def copy_mcq_text(mcq_id: int) -> str:
    """Return MCQ text formatted for easy copy-paste into Word."""
    return export_mcq_text(mcq_id)


def copy_visual_prompt(mcq_id: int) -> str:
    """Return visual prompt text for easy copy-paste."""
    db = SessionLocal()
    try:
        mcq = db.query(MCQRecord).filter(MCQRecord.id == mcq_id).first()
        if not mcq:
            return "MCQ not found."
        return mcq.visual_prompt or "No visual prompt set."
    finally:
        db.close()


def export_all_mcq(mcq_id: int) -> Optional[str]:
    """Export MCQ, visual prompt, and image info as a downloadable .txt file."""
    db = SessionLocal()
    try:
        result = (
            db.query(MCQRecord, Source, Triplet)
            .join(Source, MCQRecord.source_id == Source.id)
            .outerjoin(Triplet, MCQRecord.triplet_id == Triplet.id)
            .filter(MCQRecord.id == mcq_id)
            .first()
        )
        
        if not result:
            return None
        
        mcq, source, triplet = result
        options = json.loads(mcq.options)
        
        # Build comprehensive export text
        lines = [
            "=" * 80,
            "MCQ EXPORT",
            "=" * 80,
            "",
            f"MCQ ID: {mcq.id}",
            f"Source: {source.title or 'Untitled'} ({source.source_id})",
            f"Authors: {source.authors or 'N/A'}",
            f"Year: {source.publication_year or 'N/A'}",
            "",
            "-" * 80,
            "MCQ CONTENT",
            "-" * 80,
            "",
            f"Stem: {mcq.stem}",
            "",
            f"Question: {mcq.question}",
            "",
            "Options:",
        ]
        
        for idx, opt in enumerate(options):
            marker = " [CORRECT]" if idx == mcq.correct_option else ""
            lines.append(f"  {chr(65+idx)}) {opt}{marker}")
        
        if triplet:
            lines.extend([
                "",
                "-" * 80,
                "TRIPLET INFORMATION",
                "-" * 80,
                "",
                f"Subject: {triplet.subject}",
                f"Action: {triplet.action}",
                f"Object: {triplet.object}",
                f"Relation: {triplet.relation}",
            ])
        
        if mcq.visual_prompt:
            lines.extend([
                "",
                "-" * 80,
                "VISUAL PROMPT",
                "-" * 80,
                "",
                mcq.visual_prompt,
            ])
        
        if mcq.image_url:
            image_path = get_image_path(mcq_id)
            if image_path and image_path.exists():
                lines.extend([
                    "",
                    "-" * 80,
                    "IMAGE INFORMATION",
                    "-" * 80,
                    "",
                    f"Image Path: {mcq.image_url}",
                    f"Image File: {image_path}",
                    f"Image Status: Available",
                ])
            else:
                lines.extend([
                    "",
                    "-" * 80,
                    "IMAGE INFORMATION",
                    "-" * 80,
                    "",
                    f"Image Path: {mcq.image_url}",
                    f"Image Status: File not found",
                ])
        else:
            lines.extend([
                "",
                "-" * 80,
                "IMAGE INFORMATION",
                "-" * 80,
                "",
                "Image Status: No image available",
            ])
        
        # Create temporary file
        content = "\n".join(lines)
        temp_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.txt',
            prefix=f'mcq_{mcq_id}_',
            delete=False
        )
        temp_file.write(content)
        temp_file.close()
        
        return temp_file.name
    except Exception as e:
        logger.error(f"Error exporting MCQ {mcq_id}: {e}")
        return None
    finally:
        db.close()


def open_mcq_in_builder(mcq_id: int) -> Tuple[str, str, str]:
    """Prepare to open MCQ in Tab 2 (Builder) by selecting the source article."""
    db = SessionLocal()
    try:
        mcq = db.query(MCQRecord).filter(MCQRecord.id == mcq_id).first()
        if not mcq:
            return "", "", "MCQ not found."
        
        source = db.query(Source).filter(Source.id == mcq.source_id).first()
        if not source:
            return "", "", "Source not found."
        
        # Check if source is in pending
        pending = db.query(PendingSource).filter(PendingSource.source_id == source.id).first()
        if not pending:
            # Add to pending if not already there
            db.add(PendingSource(source_id=source.id))
            db.commit()
        
        # Format dropdown choice
        year = source.publication_year or "Year N/A"
        choice = f"{source.id} | {source.source_id} | {source.title or 'Untitled'} ({year})"
        
        return choice, f"Source {source.source_id} is now available in MCQ Builder. Switch to Tab 2 to continue.", ""
    finally:
        db.close()


def format_original_mcq(mcq: MCQRecord, source: Source, triplet: Optional[Triplet]) -> str:
    """Format MCQ for display"""
    options = json.loads(mcq.options)
    
    html = f"""
## Original MCQ
**Status:** {mcq.status.title()}

### Clinical Stem:
{mcq.stem}

### Question:
{mcq.question}

### Options:
"""
    for i, option in enumerate(options, start=1):
        marker = "(Correct) " if i - 1 == mcq.correct_option else ""
        html += f"{marker}{chr(64+i)}) {option}\n"
    
    html += f"""
### Provenance:
- **Title:** {source.title}
- **Authors:** {source.authors or 'N/A'}
- **Source ID:** {source.source_id}
"""
    if triplet:
        html += f"- **Triplet:** {triplet.subject} → {triplet.action} → {triplet.object}\n"
    return html


async def handle_request_update(update_request: str, mcq_id_state: int, model_id: str) -> str:
    """Request MCQ update from LLM"""
    if not update_request.strip():
        return "*Please describe the update you want.*"
    
    if not mcq_id_state:
        return "*Please generate an MCQ first*"
    
    try:
        session_id = await get_or_create_session()
        result = await run_agent(
            new_message=f"Update MCQ {mcq_id_state} with the following changes: {update_request}",
            user_id=DEFAULT_USER_ID,
            session_id=session_id,
            model_id=model_id,
        )
        
        # Extract updated MCQ
        updated_mcq = result.get("mcq_draft", {})
        
        # Format for display
        db = SessionLocal()
        try:
            mcq = db.query(MCQRecord).filter(MCQRecord.id == mcq_id_state).first()
            if not mcq:
                return "MCQ not found."
            
            source = db.query(Source).filter(Source.id == mcq.source_id).first()
            triplet = db.query(Triplet).filter(Triplet.id == mcq.triplet_id).first()
            
            options = updated_mcq.get("options", json.loads(mcq.options))
            
            html = f"""
## Updated MCQ (LLM Generated)
**Status:** Pending Review

### Clinical Stem:
{updated_mcq.get('stem', mcq.stem)}

### Question:
{updated_mcq.get('question', mcq.question)}

### Options:
"""
            for i, option in enumerate(options, start=1):
                marker = "(Correct) " if i - 1 == updated_mcq.get('correct_option', mcq.correct_option) else ""
                html += f"{marker}{chr(64+i)}) {option}\n"
            
            html += f"""
### Provenance:
- **Title:** {source.title}
- **Authors:** {source.authors or 'N/A'}
- **Source ID:** {source.source_id}
- **Triplet:** {triplet.subject} → {triplet.action} → {triplet.object}
"""
            return html
        finally:
            db.close()
    except Exception as e:
        return f"Error: {e}"


def handle_show_image(mcq_id: Optional[int], model_id: Optional[str] = None) -> Tuple[gr.Image, str]:
    """Generate image if needed, then load and display from media folder."""
    if not mcq_id:
        return gr.update(visible=False, value=None), "No MCQ selected."
    
    # Check if image already exists
    image_file = get_image_path(mcq_id)
    
    # If image doesn't exist, generate it first
    if not image_file or not image_file.exists():
        db = SessionLocal()
        try:
            mcq = db.query(MCQRecord).filter(MCQRecord.id == mcq_id).first()
            if not mcq:
                return gr.update(visible=False, value=None), "MCQ not found."
            
            visual_prompt = (mcq.visual_prompt or "").strip()
            if not visual_prompt:
                return gr.update(visible=False, value=None), "No visual prompt found. Accept a visual prompt first."
            
            # Generate image with model_id support
            result = generate_image_from_prompt(visual_prompt, DEFAULT_IMAGE_DIMENSION, model_id=model_id)
            if not result.success or not result.image_bytes:
                return gr.update(visible=False, value=None), f"Error generating image: {result.message}"
            
            # Save image
            image_path = save_image(mcq_id, result.image_bytes)
            mcq.image_url = image_path
            db.commit()
            
            # Return status - user needs to click again to see it
            return gr.update(visible=False, value=None), f"Image generated and saved. Click 'Show Image' again to display."
        except Exception as exc:
            return gr.update(visible=False, value=None), f"Error generating image: {exc}"
        finally:
            db.close()
    
    # Image exists, load and display it
    try:
        with Image.open(image_file) as img:
            # Convert to RGB if necessary (Gradio works better with RGB)
            if img.mode in ('RGBA', 'LA', 'P'):
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                image_copy = rgb_img.copy()
            else:
                image_copy = img.convert('RGB').copy()
        
        return gr.update(value=image_copy, visible=True), f"Image loaded from {image_file.name}"
    except Exception as exc:
        return gr.update(visible=False, value=None), f"Error loading image: {exc}"


def handle_delete_image(mcq_id: Optional[int]) -> Tuple[gr.Image, str]:
    """Delete image file and update database."""
    if not mcq_id:
        return gr.update(visible=False, value=None), "No MCQ selected."
    
    db = SessionLocal()
    try:
        mcq = db.query(MCQRecord).filter(MCQRecord.id == mcq_id).first()
        if not mcq:
            return gr.update(visible=False, value=None), "MCQ not found."
        
        deleted = delete_image(mcq_id)
        if deleted:
            mcq.image_url = None
            db.commit()
            return gr.update(visible=False, value=None), "Image deleted successfully."
        else:
            return gr.update(visible=False, value=None), "No image found to delete."
    finally:
        db.close()


def update_llm_model(model_id: str) -> Tuple[str, str]:
    """Update LLM model selection and persist state."""
    label = llm_manager.get_label(model_id)
    return f"LLM model set to: {label}", model_id


# ========== Main Interface ==========
# Legacy interface removed - see create_interface() below for the current implementation

def create_interface():
    """Updated Gradio interface with pending → builder → knowledge base flow."""
    initial_pending_html, initial_pending_page, initial_pending_info = render_pending_sources(1)

    with gr.Blocks(title="Medical MCQ Generator") as demo:
        with gr.Row():
            gr.Markdown("# Medical MCQ Generator")
            llm_selector = gr.Dropdown(
                choices=llm_manager.get_choices(),
                value=llm_manager.default_id,
                label="LLM Model",
                scale=1
            )
            llm_status = gr.Textbox(
                label="Status",
                value=f"{llm_manager.get_label(llm_manager.default_id)} selected",
                interactive=False,
                scale=2
            )
        llm_model_state = gr.State(llm_manager.default_id)

        llm_selector.change(
            fn=update_llm_model,
            inputs=llm_selector,
            outputs=[llm_status, llm_model_state]
        )

        with gr.Tabs():
            # Tab 1: Source Intake
            with gr.Tab("Source Intake"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### Search PubMed Articles (use either search or upload)")
                        pubmed_search = gr.Textbox(
                            label="Enter keywords",
                            placeholder="e.g., subdural hematoma surgery",
                            lines=1
                        )
                        search_btn = gr.Button("Search", variant="primary")
                        search_results = gr.Markdown(value="*Enter keywords and click Search*")
                        articles_state = gr.State([])
                        selection_input = gr.Textbox(
                            label="Select article numbers",
                            placeholder="Comma-separated indices (e.g., 1,3,5)",
                            interactive=False
                        )
                        select_articles_btn = gr.Button("Queue Articles", variant="primary", interactive=False)
                        selection_status = gr.Textbox(label="Status", interactive=False)

                        gr.Markdown("---")
                        gr.Markdown("### Upload PDF Document")
                        pdf_upload = gr.File(label="Upload PDF", file_types=[".pdf"])
                        upload_status = gr.Textbox(label="Upload Status", interactive=False)

                    with gr.Column(scale=1):
                        gr.Markdown("### Pending Review")
                        pending_display = gr.Markdown(value=initial_pending_html)
                        pending_info = gr.Textbox(value=initial_pending_info, label="Pagination", interactive=False)
                        pending_page_state = gr.State(initial_pending_page)
                        with gr.Row():
                            pending_prev_btn = gr.Button("◀ Prev", variant="secondary")
                            pending_next_btn = gr.Button("Next ▶", variant="secondary")
                            pending_clear_btn = gr.Button("Clear Pending", variant="stop")

                def search_wrapper(keywords):
                    articles, message = handle_pubmed_search(keywords)
                    results_text = f"{message}\n\n{format_articles_markdown(articles)}" if articles else message
                    if articles:
                        input_update = gr.update(interactive=True, value="")
                        button_update = gr.update(interactive=True)
                        status_update = gr.update(value="")
                    else:
                        input_update = gr.update(interactive=False, value="")
                        button_update = gr.update(interactive=False)
                        status_update = gr.update(value="")
                    return results_text, articles, input_update, button_update, status_update

                search_btn.click(
                    fn=search_wrapper,
                    inputs=pubmed_search,
                    outputs=[search_results, articles_state, selection_input, select_articles_btn, selection_status]
                )

                selection_event = select_articles_btn.click(
                    fn=lambda choice, articles, model_id: asyncio.run(
                        handle_article_selection_from_input(choice, articles, model_id)
                    ),
                    inputs=[selection_input, articles_state, llm_model_state],
                    outputs=[selection_status]
                )
                selection_event.then(
                    fn=refresh_pending_default,
                    outputs=[pending_display, pending_page_state, pending_info]
                )

                upload_event = pdf_upload.change(
                    fn=lambda file, model_id: handle_pdf_upload(file, model_id),
                    inputs=[pdf_upload, llm_model_state],
                    outputs=upload_status
                )
                upload_event.then(
                    fn=refresh_pending_default,
                    outputs=[pending_display, pending_page_state, pending_info]
                )

                pending_prev_btn.click(
                    fn=lambda page: handle_pending_navigation(-1, page),
                    inputs=pending_page_state,
                    outputs=[pending_display, pending_page_state, pending_info]
                )
                pending_next_btn.click(
                    fn=lambda page: handle_pending_navigation(1, page),
                    inputs=pending_page_state,
                    outputs=[pending_display, pending_page_state, pending_info]
                )
                pending_clear_btn.click(
                    fn=handle_pending_clear,
                    outputs=[pending_display, pending_page_state, pending_info]
                )

            # Tab 2: MCQ Builder
            with gr.Tab("MCQ Builder"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Pending Articles")
                        pending_article_dropdown = gr.Dropdown(
                            choices=[],
                            label="Pending Articles",
                            interactive=True,
                            visible=True,
                            value=None
                        )
                        builder_article_status = gr.Textbox(label="Builder Status", interactive=False)
                        refresh_pending_articles_btn = gr.Button("Refresh Pending Articles", variant="secondary")

                        gr.Markdown("---")
                        generate_mcq_btn = gr.Button("Generate MCQ Draft (takes a few seconds)", variant="primary")
                        mcq_feedback_input = gr.Textbox(
                            label="Reviewer Feedback",
                            placeholder="Optional instructions for refinement",
                            lines=2
                        )
                        apply_feedback_btn = gr.Button("Apply Feedback (refinement may take a few seconds)", variant="secondary")
                        accept_mcq_btn = gr.Button("Accept MCQ", variant="primary")

                        mcq_display = gr.Markdown(value="*Generate an MCQ draft to begin.*", elem_id="mcq_preview")
                        triplet_display = gr.Markdown(value="*Triplet details will appear here.*")
                        mcq_id_state = gr.State(None)
                        visual_prompt_saved_state = gr.State(False)

                        gr.Markdown("---")
                        gr.Markdown("### Visual Prompt")
                        visual_prompt_display = gr.Textbox(
                            label="Visual Prompt",
                            value="",
                            lines=4,
                            interactive=True
                        )
                        visual_triplet_display = gr.Textbox(
                            label="Visual Triplet / Notes",
                            value="",
                            interactive=False
                        )
                        accept_visual_prompt_btn = gr.Button("Accept Visual Prompt", variant="primary")
                        
                        gr.Markdown("---")
                        gr.Markdown("### Image (Auto-generated on Accept)")
                        show_image_btn = gr.Button("Show Image (first click generates, second click loads, third click displays 😞)", variant="secondary")
                        delete_image_btn = gr.Button("Delete Image", variant="secondary")
                        image_display = gr.Image(label="Generated Image", visible=False, type="pil")
                        image_status = gr.Textbox(label="Image Status", interactive=False, visible=True)

                refresh_pending_articles_btn.click(
                    fn=load_pending_articles_dropdown,
                    outputs=[pending_article_dropdown, builder_article_status]
                )

                generate_event = generate_mcq_btn.click(
                    fn=generate_mcq_for_pending_article,
                    inputs=[pending_article_dropdown, llm_model_state],
                    outputs=[mcq_display, visual_prompt_display, triplet_display]
                )
                generate_event = generate_event.then(
                    fn=lambda: False,
                    outputs=visual_prompt_saved_state
                )
                generate_event.then(
                    fn=_visual_prompt_button_state,
                    inputs=visual_prompt_saved_state,
                    outputs=accept_visual_prompt_btn
                )

                feedback_event = apply_feedback_btn.click(
                    fn=apply_mcq_feedback,
                    inputs=[pending_article_dropdown, mcq_feedback_input, llm_model_state],
                    outputs=[mcq_display, visual_prompt_display, triplet_display]
                )
                feedback_event = feedback_event.then(
                    fn=lambda: False,
                    outputs=visual_prompt_saved_state
                )
                feedback_event.then(
                    fn=_visual_prompt_button_state,
                    inputs=visual_prompt_saved_state,
                    outputs=accept_visual_prompt_btn
                )

                accept_mcq_event = accept_mcq_btn.click(
                    fn=lambda choice, prompt: handle_accept_mcq(choice, prompt),
                    inputs=[pending_article_dropdown, visual_prompt_display],
                    outputs=[builder_article_status, mcq_id_state]
                )
                accept_mcq_event = accept_mcq_event.then(
                    fn=refresh_pending_default,
                    outputs=[pending_display, pending_page_state, pending_info]
                )
                accept_mcq_event = accept_mcq_event.then(
                    fn=load_pending_articles_dropdown,
                    outputs=[pending_article_dropdown, builder_article_status]
                )
                accept_mcq_event = accept_mcq_event.then(
                    fn=load_stored_mcq_view,
                    inputs=mcq_id_state,
                    outputs=[mcq_display, triplet_display, visual_prompt_display, visual_prompt_saved_state]
                )
                accept_mcq_event.then(
                    fn=_visual_prompt_button_state,
                    inputs=visual_prompt_saved_state,
                    outputs=accept_visual_prompt_btn
                )

                visual_prompt_display.change(
                    fn=lambda _: False,
                    inputs=visual_prompt_display,
                    outputs=visual_prompt_saved_state
                ).then(
                    fn=_visual_prompt_button_state,
                    inputs=visual_prompt_saved_state,
                    outputs=accept_visual_prompt_btn
                )

                accept_visual_prompt_event = accept_visual_prompt_btn.click(
                    fn=lambda mcq_id, prompt: handle_accept_visual_prompt(mcq_id, prompt),
                    inputs=[mcq_id_state, visual_prompt_display],
                    outputs=[builder_article_status, visual_prompt_display, visual_prompt_saved_state]
                )
                accept_visual_prompt_event.then(
                    fn=_visual_prompt_button_state,
                    inputs=visual_prompt_saved_state,
                    outputs=accept_visual_prompt_btn
                )

                show_image_btn.click(
                    fn=lambda mcq_id, model_id: handle_show_image(mcq_id, model_id),
                    inputs=[mcq_id_state, llm_model_state],
                    outputs=[image_display, image_status]
                )
                
                delete_image_btn.click(
                    fn=lambda mcq_id: handle_delete_image(mcq_id),
                    inputs=mcq_id_state,
                    outputs=[image_display, image_status]
                )

            # Tab 3: Knowledge Base
            with gr.Tab("Knowledge Base"):
                initial_kb_html, initial_kb_page, initial_kb_info = render_kb_list(1, None)
                kb_page_state = gr.State(initial_kb_page)
                
                with gr.Row():
                    with gr.Column(scale=2):
                        gr.Markdown("### Search Stored MCQs (Optional)")
                        kb_search_input = gr.Textbox(
                            label="Search by PMID, title, or question text",
                            placeholder="e.g., 123456, stroke, 2023"
                        )
                        kb_search_btn = gr.Button("Search", variant="primary")
                        kb_clear_btn = gr.Button("Clear Search", variant="secondary")
                        
                        gr.Markdown("---")
                        gr.Markdown("### MCQ List")
                        kb_list_display = gr.Markdown(value=initial_kb_html)
                        kb_info = gr.Textbox(value=initial_kb_info, label="Pagination", interactive=False)
                        with gr.Row():
                            kb_prev_btn = gr.Button("◀ Prev", variant="secondary")
                            kb_next_btn = gr.Button("Next ▶", variant="secondary")
                        
                        gr.Markdown("---")
                        gr.Markdown("### View MCQ Details")
                        kb_mcq_id_input = gr.Number(
                            label="Enter MCQ ID to view details",
                            value=None,
                            precision=0,
                            interactive=True
                        )
                        kb_view_btn = gr.Button("View Details", variant="primary")
                        kb_open_builder_btn = gr.Button("Open in Builder", variant="secondary")
                    
                    with gr.Column(scale=3):
                        gr.Markdown("### MCQ Details")
                        kb_detail_display = gr.Markdown(value="*Enter an MCQ ID and click 'View Details' to see full information.*")
                        kb_triplet_display = gr.Markdown(value="")
                        kb_image_display = gr.Image(label="MCQ Image", visible=False)
                        kb_image_status = gr.Textbox(label="Image Status", interactive=False, visible=False)
                        
                        gr.Markdown("---")
                        gr.Markdown("### Export All")
                        kb_export_all_btn = gr.Button("Export All (click twice to download 😞)", variant="primary")
                        kb_export_file = gr.File(
                            label="Download Export File",
                            visible=False
                        )
                        kb_mcq_id_state = gr.State(None)
                
                # Event handlers
                def search_wrapper(query):
                    html, page, info = search_stored_mcqs(query)
                    return html, page, info
                
                def clear_search_wrapper():
                    html, page, info = render_kb_list(1, None)
                    return html, page, info, ""
                
                def navigate_kb(direction, current_page, current_query):
                    new_page = max(1, current_page + direction)
                    html, page, info = render_kb_list(new_page, current_query if current_query else None)
                    return html, page, info
                
                def view_detail_wrapper(mcq_id):
                    if not mcq_id:
                        return (
                            "*Please enter an MCQ ID.*",
                            "",
                            gr.update(visible=False, value=None),
                            "",
                            None
                        )
                    mcq_html, triplet_md, image_display, image_status = get_mcq_detail(int(mcq_id))
                    return mcq_html, triplet_md, image_display, image_status, int(mcq_id)
                
                def export_all_wrapper(mcq_id):
                    if mcq_id is None:
                        return gr.update(value=None, visible=False)
                    try:
                        mcq_id = int(mcq_id)
                        file_path = export_all_mcq(mcq_id)
                        if file_path:
                            return gr.update(value=file_path, visible=True)
                        else:
                            return gr.update(value=None, visible=False)
                    except (ValueError, TypeError) as e:
                        return gr.update(value=None, visible=False)
                
                def open_builder_wrapper(mcq_id):
                    if not mcq_id:
                        return "", "", "Please enter an MCQ ID first."
                    choice, status, _ = open_mcq_in_builder(mcq_id)
                    return choice, status
                
                kb_search_btn.click(
                    fn=search_wrapper,
                    inputs=kb_search_input,
                    outputs=[kb_list_display, kb_page_state, kb_info]
                )
                
                kb_clear_btn.click(
                    fn=clear_search_wrapper,
                    outputs=[kb_list_display, kb_page_state, kb_info, kb_search_input]
                )
                
                kb_prev_btn.click(
                    fn=lambda page, query: navigate_kb(-1, page, query),
                    inputs=[kb_page_state, kb_search_input],
                    outputs=[kb_list_display, kb_page_state, kb_info]
                )
                
                kb_next_btn.click(
                    fn=lambda page, query: navigate_kb(1, page, query),
                    inputs=[kb_page_state, kb_search_input],
                    outputs=[kb_list_display, kb_page_state, kb_info]
                )
                
                kb_view_btn.click(
                    fn=view_detail_wrapper,
                    inputs=kb_mcq_id_input,
                    outputs=[kb_detail_display, kb_triplet_display, kb_image_display, kb_image_status, kb_mcq_id_state]
                )
                
                kb_export_all_btn.click(
                    fn=export_all_wrapper,
                    inputs=kb_mcq_id_state,
                    outputs=kb_export_file
                )
                
                kb_open_builder_btn.click(
                    fn=open_builder_wrapper,
                    inputs=kb_mcq_id_input,
                    outputs=[pending_article_dropdown, builder_article_status]
                )

            # Tab 4: Placeholder
            with gr.Tab("Analytics (Coming Soon)"):
                gr.Markdown("*Analytics dashboard placeholder.*")

    return demo
