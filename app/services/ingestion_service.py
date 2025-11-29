"""PDF ingestion and text extraction service."""
from typing import Dict
from sqlalchemy.orm import Session
from app.db.models import Source
import hashlib
from app.services.pdf_section_parser import chunk_pdf_by_sections


def register_pdf_source(filename: str, pdf_bytes: bytes, db: Session) -> Dict:
    """
    Register PDF by creating parent source + chunk sources.
    Each chunk becomes a separate Source (like PubMed abstracts).
    
    Args:
        filename: Original PDF filename
        pdf_bytes: PDF file content as bytes
        db: Database session
    
    Returns:
        Dict with parent source information and chunk count
    """
    # Generate parent source_id from filename hash
    parent_source_id = f"pdf_{hashlib.md5(filename.encode()).hexdigest()[:8]}"
    
    # Check if parent already exists
    existing_parent = db.query(Source).filter(
        Source.source_id == parent_source_id,
        Source.parent_source_id.is_(None)  # Only check parent, not chunks
    ).first()
    
    if existing_parent:
        # Count existing chunks
        chunk_count = db.query(Source).filter(
            Source.parent_source_id == existing_parent.id
        ).count()
        return {
            "source_id": existing_parent.source_id,
            "title": existing_parent.title,
            "type": "pdf",
            "id": existing_parent.id,
            "chunks_created": chunk_count
        }
    
    # Chunk PDF into sections
    chunks = chunk_pdf_by_sections(pdf_bytes, filename)
    
    # Create parent source (for reference, doesn't store content)
    parent_source = Source(
        source_id=parent_source_id,
        source_type="pdf",
        title=filename,
        content="",  # Parent doesn't store content, chunks do
        parent_source_id=None,
        section_title=None
    )
    db.add(parent_source)
    db.commit()
    db.refresh(parent_source)
    
    # Create chunk sources (each like a PubMed abstract)
    chunk_sources = []
    for chunk in chunks:
        chunk_source_id = f"{parent_source_id}_chunk_{chunk['order']}"
        
        # Check if chunk already exists
        existing_chunk = db.query(Source).filter(Source.source_id == chunk_source_id).first()
        if existing_chunk:
            chunk_sources.append(existing_chunk)
            continue
        
        chunk_source = Source(
            source_id=chunk_source_id,
            source_type="pdf_chunk",
            title=f"{filename} - {chunk['section_title']}",
            content=chunk['content'],  # This is what MCQ generation uses
            parent_source_id=parent_source.id,
            section_title=chunk['section_title'],
        )
        db.add(chunk_source)
        chunk_sources.append(chunk_source)
    
    db.commit()
    
    return {
        "source_id": parent_source_id,
        "title": filename,
        "type": "pdf",
        "id": parent_source.id,
        "chunks_created": len(chunk_sources)
    }


def register_pubmed_source(article_data: Dict, db: Session) -> Dict:
    """
    Register PubMed article as source in database.
    
    Args:
        article_data: Dict with pubmed_id, title, authors, year, abstract
        db: Database session
    
    Returns:
        Dict with source information
    """
    source_id = f"PMID:{article_data['pubmed_id']}"
    
    # Check if source already exists
    existing = db.query(Source).filter(Source.source_id == source_id).first()
    if existing:
        return {
            "source_id": existing.source_id,
            "title": existing.title,
            "content": existing.content,
            "type": "pubmed",
            "id": existing.id
        }
    
    # Create source record
    source = Source(
        source_id=source_id,
        source_type="pubmed",
        title=article_data.get("title", ""),
        authors=article_data.get("authors"),
        publication_year=int(article_data["year"]) if article_data.get("year", "Unknown").isdigit() else None,
        content=article_data.get("abstract", "")
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    
    return {
        "source_id": source_id,
        "title": source.title,
        "content": source.content,
        "type": "pubmed",
        "id": source.id
    }

