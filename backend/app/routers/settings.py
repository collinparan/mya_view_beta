"""
Settings router - API endpoints for application settings management.
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

from app.config import settings

router = APIRouter()


class UserSettings(BaseModel):
    """User settings model."""
    primaryModel: Optional[str] = None
    visionModel: Optional[str] = None
    embeddingModel: Optional[str] = None
    ttsProvider: Optional[str] = "browser"
    voiceSelection: Optional[str] = "default"
    speechRate: Optional[str] = "1"
    theme: Optional[str] = "dark"
    localProcessing: Optional[bool] = True
    saveChatHistory: Optional[bool] = True
    auditLogging: Optional[bool] = True


# In-memory settings storage (in production, use database)
_user_settings: Dict[str, Any] = {
    "primaryModel": settings.PRIMARY_VLM,
    "visionModel": settings.PRIMARY_VLM,
    "embeddingModel": settings.EMBEDDING_MODEL,
    "ttsProvider": "browser",
    "voiceSelection": "default",
    "speechRate": "1",
    "theme": "dark",
    "localProcessing": True,
    "saveChatHistory": True,
    "auditLogging": True,
}


@router.get("")
async def get_settings():
    """Get current user settings."""
    return _user_settings


@router.post("")
async def update_settings(user_settings: UserSettings):
    """Update user settings."""
    global _user_settings

    # Update only provided fields
    updates = user_settings.model_dump(exclude_unset=True)
    _user_settings.update(updates)

    return {"status": "success", "settings": _user_settings}


@router.get("/models")
async def get_available_models():
    """Get available Ollama models."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.OLLAMA_HOST}/api/tags",
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                return {"models": data.get("models", [])}
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to fetch models from Ollama"
                )

    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to Ollama: {str(e)}"
        )


@router.get("/voices")
async def get_available_voices():
    """
    Get available TTS voices.
    For browser-native TTS, voices are loaded client-side.
    This endpoint returns server-side voice options if using external providers.
    """
    voices = {
        "browser": {
            "name": "Browser Native",
            "voices": [],  # Client loads these
            "description": "Uses your browser's built-in text-to-speech"
        },
        "elevenlabs": {
            "name": "ElevenLabs",
            "voices": [
                {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel", "preview": True},
                {"id": "AZnzlk1XvdvUeBnXmlld", "name": "Domi", "preview": True},
                {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella", "preview": True},
                {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni", "preview": True},
                {"id": "MF3mGyEYCl7XYWbV9V6O", "name": "Elli", "preview": True},
                {"id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh", "preview": True},
            ],
            "description": "High-quality AI voices (requires API key)"
        },
        "openai": {
            "name": "OpenAI TTS",
            "voices": [
                {"id": "alloy", "name": "Alloy"},
                {"id": "echo", "name": "Echo"},
                {"id": "fable", "name": "Fable"},
                {"id": "onyx", "name": "Onyx"},
                {"id": "nova", "name": "Nova"},
                {"id": "shimmer", "name": "Shimmer"},
            ],
            "description": "OpenAI's text-to-speech (requires API key)"
        },
        "bark": {
            "name": "Bark (Local)",
            "voices": [
                {"id": "v2/en_speaker_0", "name": "Speaker 0"},
                {"id": "v2/en_speaker_1", "name": "Speaker 1"},
                {"id": "v2/en_speaker_2", "name": "Speaker 2"},
                {"id": "v2/en_speaker_3", "name": "Speaker 3"},
                {"id": "v2/en_speaker_4", "name": "Speaker 4"},
                {"id": "v2/en_speaker_5", "name": "Speaker 5"},
                {"id": "v2/en_speaker_6", "name": "Speaker 6"},
                {"id": "v2/en_speaker_7", "name": "Speaker 7"},
                {"id": "v2/en_speaker_8", "name": "Speaker 8"},
                {"id": "v2/en_speaker_9", "name": "Speaker 9"},
            ],
            "description": "Suno's Bark model running locally (GPU recommended)"
        },
        "coqui": {
            "name": "Coqui TTS (Local)",
            "voices": [
                {"id": "tts_models/en/ljspeech/tacotron2-DDC", "name": "LJSpeech"},
                {"id": "tts_models/en/vctk/vits", "name": "VCTK Multi-speaker"},
            ],
            "description": "Open-source TTS running locally"
        },
        "sesame": {
            "name": "Sesame CSM",
            "voices": [
                {"id": "default", "name": "Default Voice"},
            ],
            "description": "Sesame's conversational speech model"
        },
    }

    return voices


@router.get("/status")
async def get_service_status():
    """Check status of various services."""
    status = {
        "ollama": {"status": "unknown", "models": 0},
        "postgres": {"status": "unknown"},
        "neo4j": {"status": "unknown"},
    }

    # Check Ollama
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.OLLAMA_HOST}/api/tags",
                timeout=5.0
            )
            if response.status_code == 200:
                data = response.json()
                status["ollama"] = {
                    "status": "connected",
                    "models": len(data.get("models", []))
                }
    except Exception:
        status["ollama"]["status"] = "disconnected"

    return status
