"""Knowledge Base service for triplet storage and retrieval."""
from sqlalchemy.orm import Session
from app.db.models import Triplet, Source
from typing import List, Dict, Optional
import json


def upsert_triplet(
    db: Session,
    subject: str,
    action: str,
    object: str,
    relation: str,
    source_id: int,
    context_sentences: List[str],  # CRITICAL
    schema_valid: bool = False,
    status: str = "pending",
) -> Triplet:
    """
    Store or update triplet in KB.
    
    Args:
        db: Database session
        subject: Triplet subject
        action: Triplet action
        object: Triplet object
        relation: Relation type from schema
        source_id: Source database ID
        context_sentences: List of 2-4 verbatim context sentences (CRITICAL)
        schema_valid: Whether triplet passes schema validation
        status: Workflow status (pending, accepted, rejected)
    
    Returns:
        Triplet model instance
    """
    # Check for duplicates
    existing = db.query(Triplet).filter(
        Triplet.subject == subject,
        Triplet.action == action,
        Triplet.object == object,
        Triplet.source_id == source_id
    ).first()
    
    if existing:
        # Update context sentences if provided
        if context_sentences:
            existing.context_sentences = json.dumps(context_sentences)
        existing.schema_valid = schema_valid
        if status:
            existing.status = status
        db.commit()
        db.refresh(existing)
        return existing
    
    # Create new triplet
    triplet = Triplet(
        subject=subject,
        action=action,
        object=object,
        relation=relation,
        source_id=source_id,
        context_sentences=json.dumps(context_sentences),
        schema_valid=schema_valid,
        status=status or "pending",
    )
    db.add(triplet)
    db.commit()
    db.refresh(triplet)
    return triplet


def get_approved_triplets(db: Session, source_id: Optional[int] = None) -> List[Triplet]:
    """
    Get all approved triplets, optionally filtered by source.
    
    Args:
        db: Database session
        source_id: Optional source ID to filter by
    
    Returns:
        List of approved Triplet instances
    """
    query = db.query(Triplet).filter(Triplet.status == "accepted")
    if source_id:
        query = query.filter(Triplet.source_id == source_id)
    return query.all()


def query_triplets_for_distractors(
    db: Session,
    subject: Optional[str] = None,
    action: Optional[str] = None,
    object: Optional[str] = None
) -> List[Triplet]:
    """
    Query KB for plausible swap triplets for distractor generation.
    See objectives_extra.txt for query types.
    
    Args:
        db: Database session
        subject: Optional subject to filter by (KB Query 1: same subject, different action/object)
        action: Optional action to filter by (KB Query 2: same action/object, different subject)
        object: Optional object to filter by (KB Query 2: same action/object, different subject)
    
    Returns:
        List of Triplet instances matching query criteria
    """
    query = db.query(Triplet).filter(Triplet.status == "accepted")
    
    # KB Query 1: Same subject, different action/object
    if subject:
        query = query.filter(Triplet.subject == subject)
    
    # KB Query 2: Same action/object, different subject
    if action and object:
        query = query.filter(Triplet.action == action, Triplet.object == object)
    
    return query.limit(10).all()

