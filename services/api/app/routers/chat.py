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
                .limit(40)
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
            prompt_messages.extend(
                {"role": row["role"], "content": row["content"]}
                for row in messages
                if row["role"] in ("user", "assistant")
            )

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
