"""
Documents router - REST endpoints for document management.
"""

from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.models.database import get_db

router = APIRouter()


class DocumentMetadata(BaseModel):
    """Document metadata model."""
    id: str
    filename: str
    document_type: str
    document_date: Optional[str] = None
    provider_name: Optional[str] = None
    family_member_id: str
    privacy_category: str = "auto_share"
    created_at: str


class DocumentUploadResponse(BaseModel):
    """Response after document upload."""
    id: str
    filename: str
    chunks_created: int
    message: str


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    family_member_id: str = Form(...),
    document_type: str = Form(default="medical_record"),
    document_date: Optional[str] = Form(default=None),
    provider_name: Optional[str] = Form(default=None),
    privacy_category: str = Form(default="auto_share"),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a medical document for processing and indexing.

    The document will be:
    1. Stored securely
    2. OCR'd if it's an image/PDF
    3. Chunked for RAG retrieval
    4. Embedded and indexed in vector store
    """
    # Validate file type
    allowed_types = [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/tiff",
        "text/plain",
    ]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file.content_type} not supported. Allowed: {allowed_types}"
        )

    # TODO: Implement document processing pipeline
    # 1. Save file
    # 2. Extract text (OCR if needed)
    # 3. Chunk text
    # 4. Generate embeddings
    # 5. Store in PostgreSQL with vectors

    doc_id = str(uuid.uuid4())

    return DocumentUploadResponse(
        id=doc_id,
        filename=file.filename,
        chunks_created=0,  # TODO: Return actual count
        message="Document uploaded. Processing pipeline not yet implemented.",
    )


@router.get("/", response_model=List[DocumentMetadata])
async def list_documents(
    family_member_id: Optional[str] = None,
    document_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List documents, optionally filtered by family member or type."""
    # TODO: Implement document listing
    return []


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get document details and metadata."""
    # TODO: Implement document retrieval
    raise HTTPException(status_code=404, detail="Document not found")


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a document and its associated chunks."""
    # TODO: Implement document deletion
    raise HTTPException(status_code=404, detail="Document not found")
