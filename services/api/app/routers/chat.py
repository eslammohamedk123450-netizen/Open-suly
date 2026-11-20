import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.core.supabase import get_supabase_admin_client
from app.services.tool_approvals import ToolApprovalStore
from app.services.ai_gateway import (
    AIProviderError,
    AIProviderNotConfigured,
    AIProviderTimeout,
    generate_reply,
)

router = APIRouter(prefix="/v1/chat", tags=["chat"])
logger = logging.getLogger("suly.api.chat")


def _build_prompt_messages(
    messages: list[dict[str, Any]],
    target_message_id: str,
) -> list[dict[str, str]]:
    """Build bounded context ending at the requested user message.

    Messages sent after the target are intentionally excluded so a retry for
    an older message cannot leak future conversation turns into its answer.
    """
    target_index = next(
        (
            index for index, row in enumerate(messages)
            if row.get("id") == target_message_id and row.get("role") == "user"
        ),
        None,
    )
    if target_index is None:
        raise HTTPException(status_code=404, detail="User message not found.")

    prompt = [
        {
            "role": "system",
            "content": (
                "You are SULY, a careful and capable AI assistant. "
                "Reply in the user's language, be clear and useful, and never claim "
                "to have performed an external action unless it was actually performed."
            ),
        }
    ]
    context_messages: list[dict[str, str]] = []
    remaining_chars = 24000
    for row in reversed(messages[max(0, target_index - 29): target_index + 1]):
        if remaining_chars <= 0:
            break
        role = row.get("role")
        content = row.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        bounded_content = content[-min(8000, remaining_chars):]
        context_messages.append({"role": role, "content": bounded_content})
        remaining_chars -= len(bounded_content)
    prompt.extend(reversed(context_messages))
    return prompt


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
            if "ai.provider.run" not in ToolApprovalStore(admin).active_scopes(user.id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="استخدام مزود الذكاء الاصطناعي يتطلب موافقة صريحة من مساحة الوكيل.",
                )

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
            prompt_messages = _build_prompt_messages(messages, str(request.message_id))

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

            try:
                answer = await generate_reply(prompt_messages)
            except AIProviderNotConfigured as exc:
                raise HTTPException(status_code=503, detail="AI provider is not configured yet.") from exc
            except AIProviderTimeout as exc:
                raise HTTPException(status_code=504, detail="AI provider timed out.") from exc
            except AIProviderError as exc:
                # Log the provider detail server-side only; the client receives
                # a generic message so upstream endpoints cannot leak to users.
                logger.warning("AI provider failed to complete the request: %s", exc)
                raise HTTPException(
                    status_code=502,
                    detail="The AI provider could not complete the request. Try again shortly.",
                ) from exc

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
                # A concurrent retry may have won the unique idempotency index;
                # any other storage failure is also handled by the fallback read
                # below, but is logged instead of being silently discarded.
                logger.exception("assistant_reply_persist_failed")

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
