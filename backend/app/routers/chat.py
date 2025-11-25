"""
Chat router - REST endpoints for chat session and message management.
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload
import uuid

from app.models.database import get_db
from app.models.chat import ChatSession, ChatMessage

router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================

class MessageCreate(BaseModel):
    """Message creation model."""
    role: str  # 'user', 'assistant', 'system'
    content: str
    has_image: bool = False
    image_path: Optional[str] = None
    model_used: Optional[str] = None


class MessageResponse(BaseModel):
    """Message response model."""
    id: str
    role: str
    content: str
    has_image: bool
    image_path: Optional[str]
    model_used: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SessionCreate(BaseModel):
    """Session creation model."""
    family_member_id: Optional[str] = None
    title: Optional[str] = None


class SessionUpdate(BaseModel):
    """Session update model."""
    title: Optional[str] = None
    sort_order: Optional[int] = None
    is_pinned: Optional[bool] = None


class SessionResponse(BaseModel):
    """Session response model."""
    id: str
    family_member_id: Optional[str]
    title: Optional[str]
    sort_order: int
    is_pinned: bool
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message: Optional[str] = None

    class Config:
        from_attributes = True


class ReorderRequest(BaseModel):
    """Request to reorder sessions."""
    session_ids: List[str]  # Ordered list of session IDs


# =============================================================================
# Session Endpoints
# =============================================================================

@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    session_data: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new chat session."""
    # Safely convert family_member_id to UUID if valid
    family_member_uuid = None
    if session_data.family_member_id and session_data.family_member_id.strip() and session_data.family_member_id != 'demo':
        try:
            family_member_uuid = uuid.UUID(session_data.family_member_id)
        except (ValueError, AttributeError):
            pass  # Invalid UUID, leave as None

    session = ChatSession(
        family_member_id=family_member_uuid,
        title=session_data.title or "New Chat",
        sort_order=0,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    return SessionResponse(
        id=str(session.id),
        family_member_id=str(session.family_member_id) if session.family_member_id else None,
        title=session.title,
        sort_order=session.sort_order,
        is_pinned=session.is_pinned,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=0,
        last_message=None,
    )


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    family_member_id: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List chat sessions, optionally filtered by family member."""
    query = select(ChatSession)

    if family_member_id and family_member_id != 'demo':
        try:
            query = query.where(ChatSession.family_member_id == uuid.UUID(family_member_id))
        except ValueError:
            pass  # Invalid UUID, return all sessions

    # Order by pinned first, then sort_order, then most recent
    query = query.order_by(
        ChatSession.is_pinned.desc(),
        ChatSession.sort_order,
        ChatSession.updated_at.desc()
    ).limit(limit)

    result = await db.execute(query)
    sessions = result.scalars().all()

    responses = []
    for session in sessions:
        # Get message count and last message
        msg_query = select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session.id)
        msg_result = await db.execute(msg_query)
        msg_count = msg_result.scalar() or 0

        # Get actual last user message content
        last_msg_query = select(ChatMessage.content).where(
            ChatMessage.session_id == session.id,
            ChatMessage.role == 'user'
        ).order_by(ChatMessage.created_at.desc()).limit(1)
        last_msg_result = await db.execute(last_msg_query)
        last_msg = last_msg_result.scalar()

        responses.append(SessionResponse(
            id=str(session.id),
            family_member_id=str(session.family_member_id) if session.family_member_id else None,
            title=session.title,
            sort_order=session.sort_order,
            is_pinned=session.is_pinned,
            created_at=session.created_at,
            updated_at=session.updated_at,
            message_count=msg_count,
            last_message=last_msg[:100] + "..." if last_msg and len(last_msg) > 100 else last_msg,
        ))

    return responses


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific chat session."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == uuid.UUID(session_id))
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get message count
    msg_query = select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session.id)
    msg_result = await db.execute(msg_query)
    msg_count = msg_result.scalar() or 0

    return SessionResponse(
        id=str(session.id),
        family_member_id=str(session.family_member_id) if session.family_member_id else None,
        title=session.title,
        sort_order=session.sort_order,
        is_pinned=session.is_pinned,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=msg_count,
    )


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    session_data: SessionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a chat session (title, sort_order, is_pinned)."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == uuid.UUID(session_id))
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Update fields if provided
    if session_data.title is not None:
        session.title = session_data.title
    if session_data.sort_order is not None:
        session.sort_order = session_data.sort_order
    if session_data.is_pinned is not None:
        session.is_pinned = session_data.is_pinned

    session.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(session)

    return SessionResponse(
        id=str(session.id),
        family_member_id=str(session.family_member_id) if session.family_member_id else None,
        title=session.title,
        sort_order=session.sort_order,
        is_pinned=session.is_pinned,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=0,
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a chat session and all its messages."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == uuid.UUID(session_id))
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.delete(session)
    return {"status": "deleted", "id": session_id}


@router.post("/sessions/reorder")
async def reorder_sessions(
    request: ReorderRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reorder sessions based on drag-and-drop."""
    for index, session_id in enumerate(request.session_ids):
        await db.execute(
            update(ChatSession)
            .where(ChatSession.id == uuid.UUID(session_id))
            .values(sort_order=index)
        )

    return {"status": "reordered", "count": len(request.session_ids)}


# =============================================================================
# Message Endpoints
# =============================================================================

@router.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
async def list_messages(
    session_id: str,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List messages in a chat session."""
    query = select(ChatMessage).where(
        ChatMessage.session_id == uuid.UUID(session_id)
    ).order_by(ChatMessage.created_at).offset(offset).limit(limit)

    result = await db.execute(query)
    messages = result.scalars().all()

    return [
        MessageResponse(
            id=str(msg.id),
            role=msg.role,
            content=msg.content,
            has_image=msg.has_image,
            image_path=msg.image_path,
            model_used=msg.model_used,
            created_at=msg.created_at,
        )
        for msg in messages
    ]


@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
async def create_message(
    session_id: str,
    message_data: MessageCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a message to a chat session."""
    # Verify session exists
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == uuid.UUID(session_id))
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Create message
    message = ChatMessage(
        session_id=uuid.UUID(session_id),
        role=message_data.role,
        content=message_data.content,
        has_image=message_data.has_image,
        image_path=message_data.image_path,
        model_used=message_data.model_used,
    )
    db.add(message)

    # Update session timestamp
    session.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(message)

    return MessageResponse(
        id=str(message.id),
        role=message.role,
        content=message.content,
        has_image=message.has_image,
        image_path=message.image_path,
        model_used=message.model_used,
        created_at=message.created_at,
    )


@router.post("/sessions/{session_id}/generate-title")
async def generate_title(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Auto-generate a title based on the first few messages."""
    from app.services.llm import LLMService

    # Get first few messages
    query = select(ChatMessage).where(
        ChatMessage.session_id == uuid.UUID(session_id)
    ).order_by(ChatMessage.created_at).limit(4)

    result = await db.execute(query)
    messages = result.scalars().all()

    if not messages:
        return {"title": "New Chat"}

    # Build context for title generation
    context = "\n".join([f"{msg.role}: {msg.content[:200]}" for msg in messages])

    # Use LLM to generate title
    llm = LLMService()
    try:
        from ollama import AsyncClient
        from app.config import settings

        client = AsyncClient(host=settings.OLLAMA_HOST)
        response = await client.chat(
            model=settings.COORDINATOR_MODEL,
            messages=[{
                "role": "user",
                "content": f"Generate a short (3-6 word) title for this conversation. Reply with ONLY the title, no quotes or punctuation:\n\n{context}"
            }],
        )
        title = response["message"]["content"].strip().strip('"\'')[:100]
    except Exception as e:
        # Fallback: use first user message
        first_user_msg = next((m for m in messages if m.role == "user"), None)
        if first_user_msg:
            title = first_user_msg.content[:50] + "..." if len(first_user_msg.content) > 50 else first_user_msg.content
        else:
            title = "New Chat"

    # Update session title
    session_result = await db.execute(
        select(ChatSession).where(ChatSession.id == uuid.UUID(session_id))
    )
    session = session_result.scalar_one_or_none()
    if session:
        session.title = title
        await db.flush()

    return {"title": title}
