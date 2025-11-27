"""
Gradio UI for Medical MCQ Generator.
Backend-integrated version.
"""
import gradio as gr
from typing import Optional, Tuple, List, Dict
import json
import asyncio
import os
from app.services.pubmed_service import search_pubmed as pubmed_search_service
from app.services.ingestion_service import register_pdf_source, register_pubmed_source
from app.services.kb_service import (
    get_approved_triplets,
    get_triplet_by_id,
    update_triplet_status
)
from app.db.database import SessionLocal, init_db
from app.db.models import Source, Triplet, MCQRecord
from app.core.runner import runner, create_new_session, get_last_session
from app.core.llm_manager import llm_manager
import time


# Initialize database
init_db()

# Session management
DEFAULT_USER_ID = "default"
current_session_id = None


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


# ========== Source Search/Upload Handlers ==========

def handle_pubmed_search(keywords: str) -> Tuple[str, List[Dict]]:
    """Search PubMed and return results with article list for selection"""
    if not keywords.strip():
        return "Please enter search keywords.", []
    
    try:
        articles = pubmed_search_service(keywords, max_results=10)
        
        if not articles:
            return f"❌ No articles found for '{keywords}'", []
        
        # Format results
        results_html = f"🔍 **Found {len(articles)} articles for '{keywords}':**\n\n"
        
        for i, article in enumerate(articles, 1):
            results_html += f"""
**{i}. {article['title']}**
- Authors: {article['authors']}
- Year: {article['year']}
- Abstract: {article['abstract'][:150]}...
- PubMed ID: {article['pubmed_id']}

"""
        
        return results_html, articles
    except Exception as e:
        return f"❌ Error searching PubMed: {str(e)}", []


def update_article_dropdown(articles: List[Dict]) -> Tuple[gr.Dropdown, gr.Button]:
    """Update article dropdown when search completes"""
    if articles and len(articles) > 0:
        choices = [f"{a['title'][:60]}... (PMID: {a['pubmed_id']})" for a in articles]
        return gr.update(choices=choices, visible=True), gr.update(visible=True)
    return gr.update(visible=False), gr.update(visible=False)


async def handle_article_selection(
    article_choice: str,
    articles_state: List[Dict],
    model_id: str,
) -> str:
    """Ingest selected PubMed article"""
    if not article_choice or not articles_state:
        return "❌ No article selected"
    
    try:
        # Extract PubMed ID from choice
        pubmed_id = article_choice.split("PMID:")[-1].strip().rstrip(")")
        
        # Find article in state
        article = next((a for a in articles_state if a['pubmed_id'] == pubmed_id), None)
        if not article:
            return "❌ Article not found"
        
        # Register in database
        db = SessionLocal()
        try:
            source_dict = register_pubmed_source(article, db)
            
            # Trigger automatic triplet extraction
            session_id = await get_or_create_session()
            from app.core.runner import run_agent
            result = await run_agent(
                new_message=f"Extract triplets from source: {source_dict['source_id']}",
                user_id=DEFAULT_USER_ID,
                session_id=session_id,
                model_id=model_id,
            )
            
            # Store extracted triplets
            extracted_triplets = result.get("extracted_triplets", [])
            source = db.query(Source).filter(Source.id == source_dict['id']).first()
            
            for triplet_data in extracted_triplets:
                from app.services.kb_service import upsert_triplet
                upsert_triplet(
                    db=db,
                    subject=triplet_data['subject'],
                    action=triplet_data['action'],
                    object=triplet_data['object'],
                    relation=triplet_data['relation'],
                    source_id=source.id,
                    context_sentences=triplet_data.get('context_sentences', []),
                    schema_valid=triplet_data.get('schema_valid', False)
                )
            
            db.commit()
            
            return f"✅ Article ingested. {len(extracted_triplets)} triplets extracted (pending review)."
        finally:
            db.close()
    except Exception as e:
        return f"❌ Error ingesting article: {str(e)}"


def handle_pdf_upload(file, model_id: str) -> str:
    """Handle PDF upload and trigger extraction"""
    if file is None:
        return "No file uploaded."
    
    try:
        # Read PDF bytes
        with open(file.name, 'rb') as f:
            pdf_bytes = f.read()
        
        # Register PDF source
        db = SessionLocal()
        try:
            source_dict = register_pdf_source(file.name, pdf_bytes, db)
            
            # Trigger automatic triplet extraction
            async def extract_triplets():
                session_id = await get_or_create_session()
                from app.core.runner import run_agent
                return await run_agent(
                    new_message=f"Extract triplets from source: {source_dict['source_id']}",
                    user_id=DEFAULT_USER_ID,
                    session_id=session_id,
                    model_id=model_id,
                )
            result = asyncio.run(extract_triplets())
            
            # Store extracted triplets
            extracted_triplets = result.get("extracted_triplets", [])
            source = db.query(Source).filter(Source.id == source_dict['id']).first()
            
            for triplet_data in extracted_triplets:
                from app.services.kb_service import upsert_triplet
                upsert_triplet(
                    db=db,
                    subject=triplet_data['subject'],
                    action=triplet_data['action'],
                    object=triplet_data['object'],
                    relation=triplet_data['relation'],
                    source_id=source.id,
                    context_sentences=triplet_data.get('context_sentences', []),
                    schema_valid=triplet_data.get('schema_valid', False)
                )
            
            db.commit()
            
            return f"✅ PDF ingested. {len(extracted_triplets)} triplets extracted (pending review)."
        finally:
            db.close()
    except Exception as e:
        return f"❌ Error uploading PDF: {str(e)}"


def refresh_ingested_sources() -> str:
    """Refresh and display ingested sources"""
    db = SessionLocal()
    try:
        sources = db.query(Source).order_by(Source.created_at.desc()).limit(10).all()
        
        if not sources:
            return "*No sources ingested yet*"
        
        html = "### 📋 Ingested Sources\n\n"
        for source in sources:
            source_type_icon = "📄" if source.source_type == "pubmed" else "📁"
            triplet_count = db.query(Triplet).filter(Triplet.source_id == source.id).count()
            html += f"""
{source_type_icon} **{source.title[:60]}...**
- Type: {source.source_type.upper()}
- ID: {source.source_id}
- Triplets: {triplet_count} extracted
---
"""
        return html
    finally:
        db.close()


# ========== Triplet Review Handlers ==========

def load_pending_triplets() -> Tuple[str, gr.Dropdown]:
    """Load pending triplets for review"""
    db = SessionLocal()
    try:
        triplets = db.query(Triplet).filter(Triplet.status == "pending").order_by(Triplet.created_at.desc()).all()
        
        if not triplets:
            return "*No triplets pending review.*", gr.update(choices=[], visible=False)
        
        html = "### Pending Triplets for Review\n\n"
        choices = []
        
        for triplet in triplets:
            source = db.query(Source).filter(Source.id == triplet.source_id).first()
            context_sentences = json.loads(triplet.context_sentences) if triplet.context_sentences else []
            
            html += f"""
### Triplet ID: {triplet.id}

**Triplet Information:**
- **Subject:** {triplet.subject}
- **Action:** {triplet.action}
- **Object:** {triplet.object}
- **Relation:** {triplet.relation}
- **Schema Valid:** {'✅' if triplet.schema_valid else '⚠️ Needs Review'}

**Provenance Evidence (Context Sentences):**
"""
            for sentence in context_sentences:
                html += f"> {sentence}\n\n"
            
            html += f"""
**📌 Provenance:**
- **Title:** {source.title if source else 'N/A'}
- **Authors:** {source.authors or 'N/A'}
- **Source ID:** {source.source_id if source else 'N/A'}

---
"""
            choices.append(f"ID {triplet.id}: {triplet.subject} → {triplet.action} → {triplet.object}")
        
        return html, gr.update(choices=choices, visible=True)
    finally:
        db.close()


def handle_triplet_accept(triplet_choice: str) -> str:
    """Accept triplet"""
    if not triplet_choice:
        return "❌ No triplet selected"
    
    try:
        triplet_id = int(triplet_choice.split(":")[0].split()[-1])
        db = SessionLocal()
        try:
            if update_triplet_status(db, triplet_id, "accepted"):
                return f"✅ Triplet {triplet_id} accepted and stored in KB."
            return f"❌ Triplet {triplet_id} not found."
        finally:
            db.close()
    except Exception as e:
        return f"❌ Error: {str(e)}"


def handle_triplet_reject(triplet_choice: str) -> str:
    """Reject triplet"""
    if not triplet_choice:
        return "❌ No triplet selected"
    
    try:
        triplet_id = int(triplet_choice.split(":")[0].split()[-1])
        db = SessionLocal()
        try:
            if update_triplet_status(db, triplet_id, "rejected"):
                return f"❌ Triplet {triplet_id} rejected."
            return f"❌ Triplet {triplet_id} not found."
        finally:
            db.close()
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ========== MCQ Review Handlers ==========

def load_approved_triplets_for_mcq() -> gr.Dropdown:
    """Load approved triplets for MCQ generation"""
    db = SessionLocal()
    try:
        triplets = get_approved_triplets(db)
        choices = [f"ID {t.id}: {t.subject} → {t.action} → {t.object}" for t in triplets]
        return gr.update(choices=choices)
    finally:
        db.close()


async def handle_generate_mcq(triplet_choice: str, model_id: str) -> Tuple[str, str, str]:
    """Generate MCQ from selected triplet"""
    if not triplet_choice:
        return "*Please select a triplet first*", "", ""
    
    try:
        triplet_id = int(triplet_choice.split(":")[0].split()[-1])
        
        db = SessionLocal()
        try:
            triplet = get_triplet_by_id(db, triplet_id)
            if not triplet:
                return "❌ Triplet not found.", "", ""
            
            source = db.query(Source).filter(Source.id == triplet.source_id).first()
            
            # Trigger MCQ generation pipeline
            session_id = await get_or_create_session()
            from app.core.runner import run_agent
            result = await run_agent(
                new_message=f"Generate MCQ from triplet {triplet_id}.",
                user_id=DEFAULT_USER_ID,
                session_id=session_id,
                model_id=model_id,
            )
            
            # Extract MCQ data from result
            mcq_draft = result.get("mcq_draft", {})
            visual_payload = result.get("visual_payload", {})
            
            # Store MCQ in database
            options = mcq_draft.get("options", [])
            mcq = MCQRecord(
                stem=mcq_draft.get("stem", ""),
                question=mcq_draft.get("question", ""),
                options=json.dumps(options),
                correct_option=mcq_draft.get("correct_option", 0),
                source_id=source.id,
                triplet_id=triplet.id,
                visual_prompt=visual_payload.get("optimized_visual_prompt"),
                visual_triplet=visual_payload.get("visual_triplet"),
                status="pending"
            )
            db.add(mcq)
            db.commit()
            db.refresh(mcq)
            
            # Format for display
            html = format_original_mcq(mcq, source, triplet)
            
            return html, mcq.visual_prompt or "", mcq.visual_triplet or ""
        finally:
            db.close()
    except Exception as e:
        return f"❌ Error generating MCQ: {str(e)}", "", ""


def format_original_mcq(mcq: MCQRecord, source: Source, triplet: Triplet) -> str:
    """Format MCQ for display"""
    options = json.loads(mcq.options)
    
    html = f"""
## 📝 Original MCQ
**Status:** {mcq.status.title()}

### Clinical Stem:
{mcq.stem}

### Question:
{mcq.question}

### Options:
"""
    for i, option in enumerate(options, start=1):
        marker = "✅" if i - 1 == mcq.correct_option else "  "
        html += f"{marker} {chr(64+i)}) {option}\n"
    
    html += f"""
### 📌 Provenance:
- **Title:** {source.title}
- **Authors:** {source.authors or 'N/A'}
- **Source ID:** {source.source_id}
- **Triplet:** {triplet.subject} → {triplet.action} → {triplet.object}
"""
    return html


async def handle_request_update(update_request: str, mcq_id_state: int, model_id: str) -> str:
    """Request MCQ update from LLM"""
    if not update_request.strip():
        return "*Please describe the update you want.*"
    
    if not mcq_id_state:
        return "*Please generate an MCQ first*"
    
    try:
        session_id = await get_or_create_session()
        from app.core.runner import run_agent
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
                return "❌ MCQ not found"
            
            source = db.query(Source).filter(Source.id == mcq.source_id).first()
            triplet = db.query(Triplet).filter(Triplet.id == mcq.triplet_id).first()
            
            options = updated_mcq.get("options", json.loads(mcq.options))
            
            html = f"""
## 📝 Updated MCQ (LLM Generated)
**Status:** Pending Review

### Clinical Stem:
{updated_mcq.get('stem', mcq.stem)}

### Question:
{updated_mcq.get('question', mcq.question)}

### Options:
"""
            for i, option in enumerate(options, start=1):
                marker = "✅" if i - 1 == updated_mcq.get('correct_option', mcq.correct_option) else "  "
                html += f"{marker} {chr(64+i)}) {option}\n"
            
            html += f"""
### 📌 Provenance:
- **Title:** {source.title}
- **Authors:** {source.authors or 'N/A'}
- **Source ID:** {source.source_id}
- **Triplet:** {triplet.subject} → {triplet.action} → {triplet.object}
"""
            return html
        finally:
            db.close()
    except Exception as e:
        return f"❌ Error: {str(e)}"


def handle_generate_image(visual_prompt: str, llm_model: str) -> Tuple[gr.Image, gr.Radio, gr.Row, str]:
    """Handle image generation (placeholder - requires external API)"""
    # Placeholder - in real implementation, call image generation API
    return (
        gr.update(visible=True, value=None, label="Generated Image (placeholder)"),
        gr.update(visible=True),
        gr.update(visible=True),
        f"🖼️ Image generation requested with {llm_model} (feature coming soon)"
    )


def update_llm_model(model_id: str) -> Tuple[str, str]:
    """Update LLM model selection and persist state."""
    label = llm_manager.get_label(model_id)
    return f"✅ LLM model set to: {label}", model_id


# ========== Main Interface ==========

def create_interface():
    """Create the main Gradio interface."""
    
    with gr.Blocks(title="Medical MCQ Generator") as demo:
        # Header with LLM Selector
        with gr.Row():
            gr.Markdown("# 🏥 Medical MCQ Generator")
            llm_selector = gr.Dropdown(
                choices=llm_manager.get_choices(),
                value=llm_manager.default_id,
                label="LLM Model",
                scale=1
            )
            llm_status = gr.Textbox(
                label="Status",
                value=f"✅ {llm_manager.get_label(llm_manager.default_id)} selected",
                interactive=False,
                scale=2
            )
        llm_model_state = gr.State(llm_manager.default_id)
        
        llm_selector.change(
            fn=update_llm_model,
            inputs=llm_selector,
            outputs=[llm_status, llm_model_state]
        )
        
        # Main Tabs
        with gr.Tabs():
            # Tab 1: Source Search/Upload
            with gr.Tab("📚 Source Search/Upload"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### Search PubMed Articles")
                        pubmed_search = gr.Textbox(
                            label="Enter keywords",
                            placeholder="e.g., diabetes treatment, metformin",
                            lines=1
                        )
                        search_btn = gr.Button("🔍 Search", variant="primary")
                        search_results = gr.Markdown(value="*Enter keywords and click Search*")
                        
                        # Article selection
                        articles_state = gr.State([])
                        article_dropdown = gr.Dropdown(
                            choices=[],
                            label="Select article to ingest",
                            visible=False
                        )
                        ingest_btn = gr.Button("📥 Ingest Selected Article", variant="primary", visible=False)
                        ingest_status = gr.Textbox(label="Ingest Status", interactive=False, visible=False)
                        
                        gr.Markdown("---")
                        gr.Markdown("### Upload PDF Document")
                        pdf_upload = gr.File(
                            label="Upload PDF",
                            file_types=[".pdf"]
                        )
                        upload_status = gr.Textbox(label="Upload Status", interactive=False)
                
                    with gr.Column(scale=1):
                        gr.Markdown("### 📋 Ingested Sources")
                        ingested_sources = gr.Markdown(value="*No sources ingested yet*")
                        refresh_sources_btn = gr.Button("🔄 Refresh Sources", variant="secondary")
                
                # Connect handlers
                def search_wrapper(keywords):
                    results_html, articles = handle_pubmed_search(keywords)
                    return results_html, articles, *update_article_dropdown(articles)
                
                search_btn.click(
                    fn=search_wrapper,
                    inputs=pubmed_search,
                    outputs=[search_results, articles_state, article_dropdown, ingest_btn]
                )
                
                ingest_btn.click(
                    fn=lambda choice, articles, model_id: asyncio.run(
                        handle_article_selection(choice, articles, model_id)
                    ),
                    inputs=[article_dropdown, articles_state, llm_model_state],
                    outputs=[ingest_status]
                ).then(
                    fn=lambda: refresh_ingested_sources(),
                    outputs=[ingested_sources]
                )
                
                pdf_upload.change(
                    fn=lambda file, model_id: handle_pdf_upload(file, model_id),
                    inputs=[pdf_upload, llm_model_state],
                    outputs=upload_status
                )
                refresh_sources_btn.click(fn=refresh_ingested_sources, outputs=ingested_sources)
            
            # Tab 2: Triplet Review
            with gr.Tab("🔍 Triplet Review"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Review Extracted Triplets")
                        refresh_triplets = gr.Button("🔄 Refresh Triplets", variant="primary")
                        triplet_display = gr.Markdown(value="*Click Refresh to load triplets*")
                        
                        triplet_dropdown = gr.Dropdown(
                            choices=[],
                            label="Select triplet to review",
                            visible=False
                        )
                        
                        with gr.Row():
                            accept_btn = gr.Button("✅ Accept", variant="primary")
                            reject_btn = gr.Button("❌ Reject")
                        
                        triplet_action_status = gr.Textbox(label="Action Status", interactive=False)
                
                def refresh_wrapper():
                    html, dropdown = load_pending_triplets()
                    return html, dropdown
                
                refresh_triplets.click(
                    fn=refresh_wrapper,
                    outputs=[triplet_display, triplet_dropdown]
                )
                
                accept_btn.click(
                    fn=handle_triplet_accept,
                    inputs=triplet_dropdown,
                    outputs=triplet_action_status
                )
                
                reject_btn.click(
                    fn=handle_triplet_reject,
                    inputs=triplet_dropdown,
                    outputs=triplet_action_status
                )
            
            # Tab 3: MCQ Review
            with gr.Tab("📝 MCQ Review"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Select Triplet for MCQ Generation")
                        triplet_for_mcq = gr.Dropdown(
                            choices=[],
                            label="Select approved triplet",
                            interactive=True
                        )
                        refresh_triplets_mcq = gr.Button("🔄 Refresh Triplets", variant="secondary")
                        
                        gr.Markdown("---")
                        gr.Markdown("### Original MCQ")
                        generate_mcq_btn = gr.Button("🔄 Generate MCQ", variant="primary")
                        original_mcq_display = gr.Markdown(value="*Select triplet and click Generate MCQ*")
                        
                        mcq_id_state = gr.State(None)
                        
                        with gr.Row():
                            approve_mcq_btn = gr.Button("✅ Approve", variant="primary")
                            reject_mcq_btn = gr.Button("❌ Reject")
                        
                        mcq_action_status = gr.Textbox(label="Action Status", interactive=False)
                        
                        gr.Markdown("---")
                        gr.Markdown("### 🎨 Optimized Visual Prompt")
                        visual_prompt_display = gr.Textbox(
                            label="Visual Prompt",
                            value="*Generate MCQ to see visual prompt*",
                            lines=4,
                            interactive=True
                        )
                        visual_triplet_display = gr.Textbox(
                            label="Visual Triplet",
                            value="",
                            interactive=False
                        )
                        generate_image_btn = gr.Button("🖼️ Generate Image", variant="primary")
                        
                        gr.Markdown("---")
                        gr.Markdown("### 🖼️ Generated Image")
                        image_display = gr.Image(label="Generated Image", visible=False)
                        image_llm_selector = gr.Radio(
                            choices=["ChatGPT 4o", "Gemini 2.5"],
                            value="ChatGPT 4o",
                            label="Generate with",
                            visible=False
                        )
                        with gr.Row(visible=False) as image_actions:
                            use_image_btn = gr.Button("✅ Use This Image", variant="primary")
                            regenerate_image_btn = gr.Button("🔄 Regenerate")
                            remove_image_btn = gr.Button("❌ Remove")
                        image_action_status = gr.Textbox(label="Image Action Status", interactive=False, visible=False)
                        
                        gr.Markdown("---")
                        gr.Markdown("### Request MCQ Update")
                        update_request = gr.Textbox(
                            label="Describe the update you want",
                            placeholder="e.g., Add more clinical context to stem",
                            lines=2
                        )
                        request_update_btn = gr.Button("🔄 Request Update", variant="primary")
                        
                        gr.Markdown("### Updated MCQ (LLM Generated)")
                        updated_mcq_display = gr.Markdown(value="*Request an update to see the LLM-generated version*")
                        
                        with gr.Row():
                            accept_update_btn = gr.Button("✅ Accept Update", variant="primary")
                            reject_update_btn = gr.Button("❌ Reject Update")
                        
                        update_action_status = gr.Textbox(label="Update Action Status", interactive=False)
                
                # Connect handlers
                refresh_triplets_mcq.click(fn=load_approved_triplets_for_mcq, outputs=triplet_for_mcq)
                
                def generate_wrapper(triplet_choice, model_id):
                    result = asyncio.run(handle_generate_mcq(triplet_choice, model_id))
                    # Extract MCQ ID from database (simplified - store in state)
                    db = SessionLocal()
                    try:
                        mcq = db.query(MCQRecord).order_by(MCQRecord.created_at.desc()).first()
                        mcq_id = mcq.id if mcq else None
                        return *result, mcq_id
                    finally:
                        db.close()
                
                generate_mcq_btn.click(
                    fn=generate_wrapper,
                    inputs=[triplet_for_mcq, llm_model_state],
                    outputs=[original_mcq_display, visual_prompt_display, visual_triplet_display, mcq_id_state]
                )
                
                generate_image_btn.click(
                    fn=handle_generate_image,
                    inputs=[visual_prompt_display, image_llm_selector],
                    outputs=[image_display, image_llm_selector, image_actions, image_action_status]
                )
                
                request_update_btn.click(
                    fn=lambda req, mcq_id, model_id: asyncio.run(
                        handle_request_update(req, mcq_id, model_id)
                    ),
                    inputs=[update_request, mcq_id_state, llm_model_state],
                    outputs=updated_mcq_display
                )
                
                approve_mcq_btn.click(fn=lambda: "✅ MCQ approved (feature coming soon)", outputs=mcq_action_status)
                reject_mcq_btn.click(fn=lambda: "❌ MCQ rejected (feature coming soon)", outputs=mcq_action_status)
                accept_update_btn.click(fn=lambda: "✅ Update accepted (feature coming soon)", outputs=update_action_status)
                reject_update_btn.click(fn=lambda: "❌ Update rejected (feature coming soon)", outputs=update_action_status)
            
            # Tab 4: Knowledge Base
            with gr.Tab("📚 Knowledge Base"):
                gr.Markdown("### Browse Approved Triplets and MCQs")
                gr.Markdown("*This feature will be implemented in a future phase*")
    
    return demo
