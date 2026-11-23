import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.core.supabase import get_supabase_admin_client
from app.services.tool_approvals import ToolApprovalStore
from app.services.ai_gateway import (
    AIProviderError,
    AIProviderNotConfigured,
    AIProviderTimeout,
    generate_reply,
)
from app.services.ai_provider_config import (
    AIProviderConfigurationUnavailable,
    ai_settings_from_config,
    read_ai_provider_config,
)

router = APIRouter(prefix="/v1/chat", tags=["chat"])
logger = logging.getLogger("suly.api.chat")

# حدود مستقلة للصفحات: المحادثات أقل كلفة، والرسائل أصغر لتقليل تضخم الذاكرة المؤقتة.
CHAT_EXPORT_CONVERSATION_PAGE_SIZE = 200
CHAT_EXPORT_MESSAGE_PAGE_SIZE = 25
CHAT_EXPORT_MAX_CONVERSATIONS = 1000
CHAT_EXPORT_MAX_MESSAGES = 10000
CHAT_EXPORT_MAX_BYTES = 2 * 1024 * 1024
_CHAT_EXPORT_RESERVED_BYTES = 512


def _export_row_size(row: dict[str, Any]) -> int:
    """حجم JSON لسجل مع مساحة بسيطة للفاصل بين السجلات."""
    return len(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 1


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
    _rate_limit: None = Depends(rate_limit("chat_respond")),
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
                stored_config = read_ai_provider_config(admin)
            except AIProviderConfigurationUnavailable as exc:
                logger.warning("ai_provider_vault_lookup_failed")
                raise HTTPException(
                    status_code=503,
                    detail="AI provider settings are unavailable.",
                ) from exc
            if stored_config is not None:
                settings = ai_settings_from_config(stored_config)

            usage_summary: dict[str, int] | None = None

            def capture_usage(value: dict[str, int]) -> None:
                nonlocal usage_summary
                usage_summary = value

            try:
                answer = await generate_reply(
                    prompt_messages,
                    on_usage=capture_usage,
                    settings_override=settings,
                )
            except AIProviderNotConfigured as exc:
                raise HTTPException(status_code=503, detail="AI provider is not configured yet.") from exc
            except AIProviderTimeout as exc:
                raise HTTPException(status_code=504, detail="AI provider timed out.") from exc
            except AIProviderError as exc:
                # Keep provider response details out of logs and API responses;
                # only the safe error class is useful for operational triage.
                logger.warning(
                    "AI provider failed to complete the request (error type: %s)",
                    type(exc).__name__,
                )
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
                                **({"usage": usage_summary} if usage_summary is not None else {}),
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
    idempotency_key: UUID | None = None


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


def _chat_admin():
    admin = get_supabase_admin_client()
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server-side Supabase secret is not configured.",
        )
    return admin




@router.get("/export")
def export_chat_data(
    user: AuthenticatedUser = Depends(get_current_user),
    _rate_limit: None = Depends(rate_limit("chat_export")),
) -> JSONResponse:
    """تصدير محادثات المالك فقط مع حذف metadata من الملف."""
    admin = _chat_admin()
    conversations: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    used_bytes = _CHAT_EXPORT_RESERVED_BYTES
    truncated = False
    truncation_reason: str | None = None

    try:
        with admin:
            # نجلب المحادثات بصفحات ثابتة وترتيب واضح.
            offset = 0
            while offset < CHAT_EXPORT_MAX_CONVERSATIONS:
                page = (
                    admin.table("conversations")
                    .select("id,title,created_at,updated_at")
                    .eq("user_id", user.id)
                    .order("created_at", desc=False)
                    .order("id", desc=False)
                    .range(
                        offset,
                        min(offset + CHAT_EXPORT_CONVERSATION_PAGE_SIZE, CHAT_EXPORT_MAX_CONVERSATIONS) - 1,
                    )
                    .execute()
                    .data
                ) or []
                if not page:
                    break
                for raw in page:
                    row = {
                        "id": raw.get("id"),
                        "title": raw.get("title"),
                        "created_at": raw.get("created_at"),
                        "updated_at": raw.get("updated_at"),
                    }
                    row_size = _export_row_size(row)
                    if used_bytes + row_size > CHAT_EXPORT_MAX_BYTES:
                        truncated = True
                        truncation_reason = "size_limit"
                        break
                    conversations.append(row)
                    used_bytes += row_size
                if truncated or len(page) < CHAT_EXPORT_CONVERSATION_PAGE_SIZE:
                    break
                offset += len(page)

            # نتحقق من وجود سجلات بعد حد المحادثات دون إضافتها.
            if not truncated and len(conversations) >= CHAT_EXPORT_MAX_CONVERSATIONS:
                extra = (
                    admin.table("conversations")
                    .select("id")
                    .eq("user_id", user.id)
                    .range(CHAT_EXPORT_MAX_CONVERSATIONS, CHAT_EXPORT_MAX_CONVERSATIONS)
                    .execute()
                    .data
                ) or []
                if extra:
                    truncated = True
                    truncation_reason = "conversation_limit"

            # نقرأ الرسائل على دفعات IDs قصيرة لتجنب استعلام ضخم.
            if not truncated:
                for batch_start in range(0, len(conversations), 100):
                    batch_ids = [row["id"] for row in conversations[batch_start:batch_start + 100]]
                    message_offset = 0
                    while True:
                        page = (
                            admin.table("messages")
                            .select("id,conversation_id,role,content,created_at")
                            .eq("user_id", user.id)
                            .in_("conversation_id", batch_ids)
                            .order("created_at", desc=False)
                            .order("id", desc=False)
                            .range(
                                message_offset,
                                message_offset + CHAT_EXPORT_MESSAGE_PAGE_SIZE - 1,
                            )
                            .execute()
                            .data
                        ) or []
                        if not page:
                            break
                        for raw in page:
                            if len(messages) >= CHAT_EXPORT_MAX_MESSAGES:
                                truncated = True
                                truncation_reason = "message_limit"
                                break
                            row = {
                                "id": raw.get("id"),
                                "conversation_id": raw.get("conversation_id"),
                                "role": raw.get("role"),
                                "content": raw.get("content"),
                                "created_at": raw.get("created_at"),
                            }
                            row_size = _export_row_size(row)
                            if used_bytes + row_size > CHAT_EXPORT_MAX_BYTES:
                                truncated = True
                                truncation_reason = "size_limit"
                                break
                            messages.append(row)
                            used_bytes += row_size
                        if truncated or len(page) < CHAT_EXPORT_MESSAGE_PAGE_SIZE:
                            break
                        message_offset += len(page)
                    if truncated:
                        break
    except HTTPException:
        raise
    except Exception as exc:
        # لا نسجل محتوى المحادثات أو استثناءات قد تحمل بيانات المستخدم.
        logger.warning("chat_export_failed")
        raise HTTPException(status_code=503, detail="تعذر تجهيز تصدير المحادثات الآن.") from exc

    payload: dict[str, Any] = {
        "export_version": 1,
        "scope": "chat",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "conversation_count": len(conversations),
        "message_count": len(messages),
        "truncated": truncated,
        "truncation_reason": truncation_reason,
        "conversations": conversations,
        "messages": messages,
    }
    # نتحقق من الحجم النهائي الدقيق؛ reserve bytes يغطي غلاف JSON.
    while len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > CHAT_EXPORT_MAX_BYTES:
        if messages:
            messages.pop()
            truncation_reason = "size_limit"
        elif conversations:
            conversations.pop()
            truncation_reason = "size_limit"
        else:
            break
        truncated = True
        payload.update({
            "conversation_count": len(conversations),
            "message_count": len(messages),
            "truncated": truncated,
            "truncation_reason": truncation_reason,
        })
    filename = datetime.now(timezone.utc).strftime("suly-chat-export-%Y%m%d.json")
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, private",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
    _rate_limit: None = Depends(rate_limit("chat_conversations")),
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
    _rate_limit: None = Depends(rate_limit("chat_messages")),
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
            message_id = str(request.idempotency_key) if request.idempotency_key else None

            def find_existing() -> list[dict[str, Any]]:
                if message_id is None:
                    return []
                return (
                    admin.table("messages")
                    .select("id,conversation_id,user_id,role,content,metadata,created_at")
                    .eq("id", message_id)
                    .eq("conversation_id", str(conversation_id))
                    .eq("user_id", user.id)
                    .limit(1)
                    .execute()
                    .data
                ) or []

            def reuse_or_conflict(rows: list[dict[str, Any]]) -> dict[str, Any]:
                existing = rows[0]
                if existing.get("role") == "user" and existing.get("content") == content:
                    return existing
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This message retry conflicts with an existing message.",
                )

            existing = find_existing()
            if existing:
                return reuse_or_conflict(existing)

            payload = {
                "conversation_id": str(conversation_id),
                "user_id": user.id,
                "role": "user",
                "content": content,
                "metadata": {},
            }
            if message_id is not None:
                payload["id"] = message_id
            try:
                rows = admin.table("messages").insert(payload).execute().data
            except Exception as insert_error:
                # A concurrent retry can lose the primary-key race after both
                # requests observed no prior row; return the winner if it matches.
                if message_id is None:
                    raise
                try:
                    duplicate = find_existing()
                except Exception:
                    raise insert_error
                if duplicate:
                    return reuse_or_conflict(duplicate)
                raise
        if not rows:
            raise HTTPException(status_code=503, detail="Message was not saved.")
        return rows[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not save message.") from exc



@router.patch("/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: UUID,
    request: RenameConversationRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Rename only a conversation owned by the authenticated user."""
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Conversation title cannot be blank.")
    admin = _chat_admin()
    try:
        with admin:
            rows = (
                admin.table("conversations")
                .update({"title": title})
                .eq("id", str(conversation_id))
                .eq("user_id", user.id)
                .select("id,user_id,title,created_at,updated_at")
                .execute()
                .data
            )
        if not rows:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        return rows[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not rename conversation.") from exc


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, bool]:
    """Delete only an owned conversation; message cleanup follows the DB FK policy."""
    admin = _chat_admin()
    try:
        with admin:
            rows = (
                admin.table("conversations")
                .delete()
                .eq("id", str(conversation_id))
                .eq("user_id", user.id)
                .select("id")
                .execute()
                .data
            )
        if not rows:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        return {"deleted": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not delete conversation.") from exc
