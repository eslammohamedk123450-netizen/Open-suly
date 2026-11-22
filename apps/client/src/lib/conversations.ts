import { supabase } from "@/lib/supabase";

const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, "");

export type Conversation = {
  id: string;
  user_id: string;
  title: string;
  project_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type MessageRole = "user" | "assistant" | "system" | "tool";

export type ChatMessage = {
  id: string;
  conversation_id: string;
  user_id: string;
  role: MessageRole;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

/**
 * All conversation writes and reads go through the authenticated SULY API.
 * The client never supplies a user_id; the API derives ownership from the
 * verified Supabase access token and applies owner filters server-side.
 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!apiBaseUrl) throw new Error("عنوان خدمة SULY API غير مضبوط بعد.");
  if (!supabase) throw new Error("اتصال الحساب غير مهيأ.");
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session) throw new Error("انتهت جلسة الدخول. سجّل الدخول مرة أخرى.");

  const response = await fetch(apiBaseUrl + path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + data.session.access_token,
      ...(init.headers ?? {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload && typeof payload.detail === "string"
      ? payload.detail
      : "تعذر تنفيذ طلب المحادثة.";
    throw new Error(detail);
  }
  return payload as T;
}

export async function listConversations(): Promise<Conversation[]> {
  const payload = await request<{ items: Conversation[] }>("/v1/chat/conversations?limit=100");
  return payload.items ?? [];
}

export async function createConversation(title = "محادثة جديدة", projectId?: string): Promise<Conversation> {
  const cleanTitle = title.trim() || "محادثة جديدة";
  if (cleanTitle.length > 200) throw new Error("عنوان المحادثة أطول من الحد المسموح.");
  return request<Conversation>("/v1/chat/conversations", {
    method: "POST",
    body: JSON.stringify({ title: cleanTitle, ...(projectId ? { project_id: projectId } : {}) }),
  });
}

export async function listMessages(conversationId: string): Promise<ChatMessage[]> {
  const payload = await request<{ items: ChatMessage[] }>(
    "/v1/chat/conversations/" + encodeURIComponent(conversationId) + "/messages?limit=200",
  );
  return payload.items ?? [];
}

export async function sendUserMessage(conversationId: string, content: string): Promise<ChatMessage> {
  const cleanContent = content.trim();
  if (!cleanContent) throw new Error("اكتب رسالة قبل الإرسال.");
  if (cleanContent.length > 100000) throw new Error("الرسالة أطول من الحد المسموح.");
  return request<ChatMessage>(
    "/v1/chat/conversations/" + encodeURIComponent(conversationId) + "/messages",
    { method: "POST", body: JSON.stringify({ content: cleanContent }) },
  );
}

export async function renameConversation(conversationId: string, title: string): Promise<Conversation> {
  const cleanTitle = title.trim();
  if (!cleanTitle || cleanTitle.length > 200) {
    throw new Error("عنوان المحادثة يجب أن يكون بين حرف واحد و200 حرف.");
  }
  return request<Conversation>(
    "/v1/chat/conversations/" + encodeURIComponent(conversationId),
    { method: "PATCH", body: JSON.stringify({ title: cleanTitle }) },
  );
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await request<{ deleted: boolean }>(
    "/v1/chat/conversations/" + encodeURIComponent(conversationId),
    { method: "DELETE" },
  );
}
