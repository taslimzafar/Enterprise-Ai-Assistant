from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user, RoleChecker
from app.db.models.user import User
from app.db.models.membership import Membership
from app.schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    ConversationResponse,
    MessageResponse,
    ChatStreamRequest,
)
from app.services.chat import ChatService

router = APIRouter()
chat_service = ChatService()

# Ensure any organization member with role >= VIEWER can use conversations
require_viewer = RoleChecker(["OWNER", "ADMIN", "MEMBER", "VIEWER"])


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    org_id: str,
    payload: ConversationCreate = ConversationCreate(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_viewer),
):
    """Create a new persistent conversation for the authenticated user and organization."""
    conversation = await chat_service.create_conversation(
        db=db,
        organization_id=org_id,
        user_id=current_user.id,
        title=payload.title,
    )
    return conversation


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_viewer),
):
    """List all conversations for the authenticated user within the organization."""
    conversations = await chat_service.list_conversations(
        db=db,
        organization_id=org_id,
        user_id=current_user.id,
    )
    return conversations


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    org_id: str,
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(require_viewer),
):
    """Retrieve a single conversation ensuring organization isolation."""
    conversation = await chat_service.get_conversation(
        db=db,
        conversation_id=conversation_id,
        organization_id=org_id,
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found in this organization",
        )
    return conversation


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    org_id: str,
    payload: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(require_viewer),
):
    """Rename or update the title of an existing conversation."""
    conversation = await chat_service.update_conversation_title(
        db=db,
        conversation_id=conversation_id,
        organization_id=org_id,
        title=payload.title,
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found in this organization",
        )
    return conversation


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    org_id: str,
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(require_viewer),
):
    """Delete a conversation and its messages cascade."""
    deleted = await chat_service.delete_conversation(
        db=db,
        conversation_id=conversation_id,
        organization_id=org_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found in this organization",
        )
    return None


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_conversation_messages(
    conversation_id: str,
    org_id: str,
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(require_viewer),
):
    """Fetch message history for a conversation."""
    messages = await chat_service.get_messages(
        db=db,
        conversation_id=conversation_id,
        organization_id=org_id,
    )
    return messages


@router.post("/{conversation_id}/stream")
async def stream_chat(
    conversation_id: str,
    org_id: str,
    payload: ChatStreamRequest,
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_viewer),
):
    """Stream real-time assistant tokens and citations via Server-Sent Events (SSE)."""
    user_role = membership.role.value if hasattr(membership.role, "value") else str(membership.role)
    generator = chat_service.stream_chat_response(
        conversation_id=conversation_id,
        user_text=payload.message,
        organization_id=org_id,
        user_id=current_user.id,
        user_role=user_role,
    )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
