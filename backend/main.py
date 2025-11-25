"""
Mya View - FastAPI Backend
Your personal health companion powered by Mya, helping your family prepare for doctor visits,
track conditions/medications, and ask better questions during appointments.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import structlog

from app.config import settings
from app.routers import chat, vision, documents, family, graph, graph_rag, timeline, ccd
from app.routers import settings as settings_router
from app.services.llm import LLMService
from app.models.database import init_db, close_db

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info("Starting Mya View API", version="0.1.0")

    # Initialize database connections
    await init_db()
    logger.info("Database connections initialized")

    # Initialize LLM service (preload models if configured)
    app.state.llm_service = LLMService()
    await app.state.llm_service.initialize()
    logger.info("LLM service initialized")

    yield

    # Shutdown
    logger.info("Shutting down Mya View API")
    await close_db()


# Create FastAPI application
app = FastAPI(
    title="Mya View",
    description="Your personal health companion powered by Mya - track conditions, prepare for doctor visits, and ask better questions",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# API Routes
# =============================================================================

# Include routers
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(vision.router, prefix="/api/vision", tags=["Vision"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(family.router, prefix="/api/family", tags=["Family"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])
app.include_router(graph.router, prefix="/api/graph", tags=["Graph"])
app.include_router(graph_rag.router, prefix="/api/graphrag", tags=["GraphRAG"])
app.include_router(timeline.router, prefix="/api/timeline", tags=["Timeline"])
app.include_router(ccd.router, prefix="/api/ccd", tags=["CCD"])


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker and monitoring."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "services": {
            "api": "up",
            # Add database and LLM status checks here
        }
    }


@app.get("/api/config")
async def get_config():
    """Return non-sensitive configuration for frontend."""
    return {
        "primary_vlm": settings.PRIMARY_VLM,
        "features": {
            "vision": True,
            "rag": True,
            "graph_rag": True,
        }
    }


# =============================================================================
# WebSocket Endpoints
# =============================================================================

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for streaming chat.

    Message format:
    {
        "type": "chat",
        "family_member_id": "uuid",
        "message": "user message",
        "session_id": "optional-session-uuid",
        "history": [{"role": "user"|"assistant", "content": "..."}]
    }

    Response format (streamed):
    {
        "type": "token" | "done" | "error" | "context",
        "content": "...",
        "metadata": {...}
    }
    """
    await websocket.accept()
    logger.info("WebSocket chat connection established")

    try:
        while True:
            data = await websocket.receive_json()

            # Get LLM service from app state
            llm_service: LLMService = app.state.llm_service

            # Stream response with conversation history
            async for chunk in llm_service.stream_chat(
                message=data.get("message", ""),
                family_member_id=data.get("family_member_id"),
                session_id=data.get("session_id"),
                history=data.get("history", []),
            ):
                await websocket.send_json(chunk)

    except WebSocketDisconnect:
        logger.info("WebSocket chat connection closed")
    except Exception as e:
        logger.error("WebSocket error", error=str(e))
        await websocket.send_json({
            "type": "error",
            "content": str(e)
        })


@app.websocket("/ws/vision")
async def websocket_vision(websocket: WebSocket):
    """
    WebSocket endpoint for vision/image analysis.

    Message format:
    {
        "type": "vision",
        "family_member_id": "uuid",
        "image_b64": "base64-encoded-image",
        "prompt": "optional prompt"
    }
    """
    await websocket.accept()
    logger.info("WebSocket vision connection established")

    try:
        while True:
            data = await websocket.receive_json()

            llm_service: LLMService = app.state.llm_service

            async for chunk in llm_service.stream_vision(
                image_b64=data.get("image_b64", ""),
                prompt=data.get("prompt", "Describe what you see in this image."),
                family_member_id=data.get("family_member_id"),
            ):
                await websocket.send_json(chunk)

    except WebSocketDisconnect:
        logger.info("WebSocket vision connection closed")
    except Exception as e:
        logger.error("WebSocket vision error", error=str(e))
        await websocket.send_json({
            "type": "error",
            "content": str(e)
        })


# =============================================================================
# Static Files (Frontend)
# =============================================================================

# Mount static files
if os.path.exists("static"):
    # Serve app.js explicitly
    @app.get("/app.js")
    async def serve_app_js():
        """Serve the frontend JavaScript."""
        return FileResponse("static/app.js", media_type="application/javascript")

    # Mount assets folder if it exists
    if os.path.exists("static/assets"):
        app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

    @app.get("/")
    async def serve_frontend():
        """Serve the frontend single-page application."""
        return FileResponse("static/index.html")

    @app.get("/voice")
    async def serve_voice():
        """Serve the voice assistant page."""
        return FileResponse("static/voice.html")

    @app.get("/settings")
    async def serve_settings():
        """Serve the settings page."""
        return FileResponse("static/settings.html")

    @app.get("/camera")
    async def serve_camera():
        """Serve the live camera vision page."""
        return FileResponse("static/camera.html")

    @app.get("/graph")
    async def serve_graph():
        """Serve the graph explorer page."""
        return FileResponse("static/graph.html")

    @app.get("/timeline")
    async def serve_timeline():
        """Serve the health timeline page."""
        return FileResponse("static/timeline.html")

    @app.get("/ccd-import")
    async def serve_ccd_import():
        """Serve the CCD import and review page."""
        return FileResponse("static/ccd_import.html")


# =============================================================================
# Development server
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD,
        log_level=settings.LOG_LEVEL.lower(),
    )
