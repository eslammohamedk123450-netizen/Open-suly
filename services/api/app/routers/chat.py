from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.core.supabase import get_supabase_admin_client
from app.services.ai_gateway import (
    AIProviderError,
    AIProviderNotConfigured,
    AIProviderTimeout,
    generate_reply,
)

router = APIRouter(prefix="/v1/chat", tags=["chat"])


class ChatRespondRequest(BaseModel):
    conversation_id: UUID
    message_id: UUID


@router.post("/respond")
async def respond_to_message(
    request: ChatRespondRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate and persist one assistant reply for an owned user message."""
    admin = get_supabase_admin_client()
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server-side Supabase secret is not configured.",
        )

    settings = get_settings()
    try:
        with admin:
            owned_conversation = (
                admin.table("conversations")
                .select("id")
                .eq("id", str(request.conversation_id))
                .eq("user_id", user.id)
                .limit(1)
                .execute()
                .data
            )
            if not owned_conversation:
                raise HTTPException(status_code=404, detail="Conversation not found.")

            rows = (
                admin.table("messages")
                .select("id,user_id,role,content,metadata,created_at,conversation_id")
                .eq("conversation_id", str(request.conversation_id))
                .eq("user_id", user.id)
                .order("created_at", desc=True)
                .limit(30)
                .execute()
                .data
            )
            messages = list(reversed(rows or []))
            target = next((row for row in messages if row["id"] == str(request.message_id)), None)
            if target is None or target["role"] != "user":
                raise HTTPException(status_code=404, detail="User message not found.")

            existing = next(
                (
                    row for row in messages
                    if row["role"] == "assistant"
                    and (row.get("metadata") or {}).get("in_reply_to") == str(request.message_id)
                ),
                None,
            )
            if existing is not None:
                return existing

            prompt_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are SULY, a careful and capable AI assistant. "
                        "Reply in the user's language, be clear and useful, and never claim "
                        "to have performed an external action unless it was actually performed."
                    ),
                }
            ]
            # Bound prompt size before sending user content to any provider.
            context_messages: list[dict[str, str]] = []
            remaining_chars = 24000
            for row in reversed(messages[-30:]):
                if remaining_chars <= 0:
                    break
                if row["role"] not in ("user", "assistant"):
                    continue
                content = row["content"][-min(8000, remaining_chars):]
                context_messages.append({"role": row["role"], "content": content})
                remaining_chars -= len(content)
            prompt_messages.extend(reversed(context_messages))

            try:
                answer = await generate_reply(prompt_messages)
            except AIProviderNotConfigured as exc:
                raise HTTPException(status_code=503, detail="AI provider is not configured yet.") from exc
            except AIProviderTimeout as exc:
                raise HTTPException(status_code=504, detail="AI provider timed out.") from exc
            except AIProviderError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc

            try:
                inserted = (
                    admin.table("messages")
                    .insert(
                        {
                            "conversation_id": str(request.conversation_id),
                            "user_id": user.id,
                            "role": "assistant",
                            "content": answer,
                            "metadata": {
                                "in_reply_to": str(request.message_id),
                                "provider": settings.ai_provider,
                                "model": settings.ai_model,
                            },
                        }
                    )
                    .execute()
                    .data
                )
                if inserted:
                    return inserted[0]
            except Exception:
                # A concurrent retry may have won the unique idempotency index.
                pass

            existing_after_race = (
                admin.table("messages")
                .select("*")
                .eq("conversation_id", str(request.conversation_id))
                .eq("user_id", user.id)
                .eq("role", "assistant")
                .contains("metadata", {"in_reply_to": str(request.message_id)})
                .limit(1)
                .execute()
                .data
            )
            if existing_after_race:
                return existing_after_race[0]
            raise HTTPException(status_code=502, detail="The assistant response could not be saved.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Chat storage is temporarily unavailable.") from exc



class CreateConversationRequest(BaseModel):
    title: str | None = None


class AddUserMessageRequest(BaseModel):
    content: str


def _chat_admin():
    admin = get_supabase_admin_client()
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server-side Supabase secret is not configured.",
        )
    return admin


@router.get("/conversations")
def list_conversations(
    limit: int = 30,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 100.")
    admin = _chat_admin()
    try:
        with admin:
            rows = (
                admin.table("conversations")
                .select("id,user_id,title,created_at,updated_at")
                .eq("user_id", user.id)
                .order("updated_at", desc=True)
                .limit(limit)
                .execute()
                .data
            )
        return {"items": rows or []}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load conversations.") from exc


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
def create_conversation(
    request: CreateConversationRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    title = (request.title or "محادثة جديدة").strip()
    if not title or len(title) > 200:
        raise HTTPException(status_code=422, detail="Conversation title must be 1–200 characters.")
    admin = _chat_admin()
    try:
        with admin:
            rows = (
                admin.table("conversations")
                .insert({"user_id": user.id, "title": title})
                .execute()
                .data
            )
        if not rows:
            raise HTTPException(status_code=503, detail="Conversation was not created.")
        return rows[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not create conversation.") from exc


@router.get("/conversations/{conversation_id}/messages")
def list_conversation_messages(
    conversation_id: UUID,
    limit: int = 100,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 200.")
    admin = _chat_admin()
    try:
        with admin:
            owned = (
                admin.table("conversations")
                .select("id")
                .eq("id", str(conversation_id))
                .eq("user_id", user.id)
                .limit(1)
                .execute()
                .data
            )
            if not owned:
                raise HTTPException(status_code=404, detail="Conversation not found.")
            rows = (
                admin.table("messages")
                .select("id,conversation_id,user_id,role,content,metadata,created_at")
                .eq("conversation_id", str(conversation_id))
                .eq("user_id", user.id)
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
                .data
            )
        return {"items": rows or []}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load messages.") from exc


@router.post("/conversations/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
def add_user_message(
    conversation_id: UUID,
    request: AddUserMessageRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    content = request.content.strip()
    if not content or len(content) > 100000:
        raise HTTPException(status_code=422, detail="Message content must be 1–100000 characters.")
    admin = _chat_admin()
    try:
        with admin:
            owned = (
                admin.table("conversations")
                .select("id,title")
                .eq("id", str(conversation_id))
                .eq("user_id", user.id)
                .limit(1)
                .execute()
                .data
            )
            if not owned:
                raise HTTPException(status_code=404, detail="Conversation not found.")
            rows = (
                admin.table("messages")
                .insert({
                    "conversation_id": str(conversation_id),
                    "user_id": user.id,
                    "role": "user",
                    "content": content,
                    "metadata": {},
                })
                .execute()
                .data
            )
        if not rows:
            raise HTTPException(status_code=503, detail="Message was not saved.")
        return rows[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not save message.") from exc
