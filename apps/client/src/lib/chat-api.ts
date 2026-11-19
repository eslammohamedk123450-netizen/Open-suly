import { supabase } from "@/lib/supabase";
import type { ChatMessage } from "@/lib/conversations";

const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, "");

export async function requestAssistantReply(conversationId: string, messageId: string): Promise<ChatMessage> {
  if (!apiBaseUrl) throw new Error("خدمة الردود لم يتم نشرها أو ضبط عنوانها بعد.");
  if (!supabase) throw new Error("اتصال الحساب غير مهيأ.");

  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session) throw new Error("انتهت جلسة الدخول. سجّل الدخول مرة أخرى.");

  const response = await fetch(apiBaseUrl + "/v1/chat/respond", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + data.session.access_token,
    },
    body: JSON.stringify({ conversation_id: conversationId, message_id: messageId }),
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof payload.detail === "string" ? payload.detail : "تعذر الحصول على رد من SULY الآن.");
  }
  return payload as ChatMessage;
}
