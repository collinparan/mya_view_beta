"""
Vision router - REST endpoints for image analysis.
"""

from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
import base64

router = APIRouter()


class VisionAnalysis(BaseModel):
    """Vision analysis response model."""
    analysis: str
    document_type: Optional[str] = None
    extracted_text: Optional[str] = None
    model_used: str


@router.post("/analyze", response_model=VisionAnalysis)
async def analyze_image(
    file: UploadFile = File(...),
    prompt: str = Form(default="Describe what you see in this image."),
    family_member_id: Optional[str] = Form(default=None),
):
    """
    Analyze an uploaded image.
    For streaming analysis, use WebSocket endpoint /ws/vision
    """
    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    # Read and encode image
    contents = await file.read()
    image_b64 = base64.b64encode(contents).decode("utf-8")

    # TODO: Implement non-streaming vision analysis
    raise HTTPException(
        status_code=501,
        detail="Use WebSocket endpoint /ws/vision for vision functionality"
    )


@router.post("/extract-text")
async def extract_text_from_image(
    file: UploadFile = File(...),
):
    """Extract text from an image using OCR."""
    # TODO: Implement OCR
    raise HTTPException(status_code=501, detail="OCR not yet implemented")
