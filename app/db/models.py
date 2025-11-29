"""SQLAlchemy models for Medical MCQ Generator."""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from app.db.database import Base  # Base is defined in database.py


class Source(Base):
    __tablename__ = "sources"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(256), unique=True)  # PubMed ID or filename
    source_type: Mapped[str] = mapped_column(String(20))  # "pubmed", "pdf", or "pdf_chunk"
    title: Mapped[str | None] = mapped_column(String(512))
    authors: Mapped[str | None] = mapped_column(String(512))
    publication_year: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)  # Abstract or PDF chunk text
    parent_source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)  # For PDF chunks
    section_title: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Section name for PDF chunks
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    
    triplets: Mapped[list["Triplet"]] = relationship(back_populates="source")
    mcqs: Mapped[list["MCQRecord"]] = relationship(back_populates="source")
    pending_entries: Mapped[list["PendingSource"]] = relationship(back_populates="source")
    parent_source: Mapped["Source"] = relationship("Source", remote_side=[id], backref="child_sources")


class Triplet(Base):
    __tablename__ = "triplets"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(256))
    action: Mapped[str] = mapped_column(String(128))
    object: Mapped[str] = mapped_column(String(256))
    relation: Mapped[str] = mapped_column(String(128))  # From schema.yaml
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    context_sentences: Mapped[str] = mapped_column(Text)  # JSON array of sentences (CRITICAL)
    schema_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, accepted, rejected
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    
    source: Mapped["Source"] = relationship(back_populates="triplets")
    mcqs: Mapped[list["MCQRecord"]] = relationship(back_populates="triplet")


class MCQRecord(Base):
    __tablename__ = "mcq_records"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    stem: Mapped[str] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[str] = mapped_column(Text)  # JSON array of 5 options
    correct_option: Mapped[int] = mapped_column(Integer)  # 0-4 index
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    triplet_id: Mapped[int] = mapped_column(ForeignKey("triplets.id"))
    visual_prompt: Mapped[str | None] = mapped_column(Text)  # Optimized Visual Prompt
    visual_triplet: Mapped[str | None] = mapped_column(String(512))  # Visual triplet string
    image_url: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, approved, rejected
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    
    source: Mapped["Source"] = relationship(back_populates="mcqs")
    triplet: Mapped["Triplet"] = relationship(back_populates="mcqs")


class PendingSource(Base):
    __tablename__ = "pending_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), unique=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    source: Mapped["Source"] = relationship(back_populates="pending_entries")

