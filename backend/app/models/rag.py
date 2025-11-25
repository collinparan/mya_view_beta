"""
RAG Data Models - Document chunks and embeddings for vector search.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Integer, DateTime, Text, Float, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
import uuid

from app.models.database import Base


class DocumentChunk(Base):
    """
    Represents a chunk of a document with its embedding for RAG retrieval.

    Each medical document is split into chunks that can be semantically searched
    using vector similarity to provide relevant context for LLM responses.
    """
    __tablename__ = "document_chunks"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Document metadata
    source_document_id = Column(String(255), nullable=False, index=True)  # Links to Neo4j or file
    source_filename = Column(String(512), nullable=True)
    document_type = Column(String(100), nullable=False)  # lab_result, interpretation, prescription, etc.
    family_member_id = Column(String(255), nullable=False, index=True)  # Which family member this belongs to

    # Chunk content
    content = Column(Text, nullable=False)  # The actual text chunk
    chunk_index = Column(Integer, nullable=False)  # Position in original document (0-indexed)
    total_chunks = Column(Integer, nullable=False)  # Total chunks in document

    # Embedding (384 dimensions for all-MiniLM-L6-v2, 1024 for BGE-M3)
    embedding = Column(Vector(384), nullable=True)  # Will be populated by embedding service

    # Metadata for better retrieval
    metadata = Column(JSONB, nullable=True)  # Store things like: patient_name, test_date, provider, etc.

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # For ranking/scoring
    relevance_score = Column(Float, nullable=True)  # Computed at query time, not stored

    __table_args__ = (
        # Index for efficient family member queries
        Index('ix_document_chunks_family_member_type', 'family_member_id', 'document_type'),
        # Index for efficient document reconstruction
        Index('ix_document_chunks_source_index', 'source_document_id', 'chunk_index'),
    )

    def __repr__(self):
        return f"<DocumentChunk(id={self.id}, source={self.source_document_id}, chunk={self.chunk_index}/{self.total_chunks})>"


class EmbeddingModel(Base):
    """
    Tracks which embedding models have been used.
    Allows for model migration and versioning.
    """
    __tablename__ = "embedding_models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name = Column(String(255), nullable=False, unique=True)  # e.g., "all-MiniLM-L6-v2"
    dimensions = Column(Integer, nullable=False)  # Embedding dimensions
    is_active = Column(Integer, nullable=False, default=1)  # Whether this is currently in use
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<EmbeddingModel(name={self.model_name}, dims={self.dimensions})>"
