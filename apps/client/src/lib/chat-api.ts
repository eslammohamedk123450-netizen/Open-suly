import { supabase } from "@/lib/supabase";
import type { ChatMessage } from "@/lib/conversations";

const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, "");

async function accessToken(): Promise<string> {
  if (!apiBaseUrl) throw new Error("خدمة الردود لم يتم نشرها أو ضبط عنوانها بعد.");
  if (!supabase) throw new Error("اتصال الحساب غير مهيأ.");
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session) throw new Error("انتهت جلسة الدخول. سجّل الدخول مرة أخرى.");
  return data.session.access_token;
}

function responseError(payload: unknown): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return "تعذر الحصول على رد من SULY الآن.";
}

export async function requestAssistantReply(
  conversationId: string, messageId: string, signal?: AbortSignal,
): Promise<ChatMessage> {
  const token = await accessToken();
  const response = await fetch(apiBaseUrl + "/v1/chat/respond", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + token,
    },
    body: JSON.stringify({ conversation_id: conversationId, message_id: messageId }),
    signal,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(responseError(payload));
  return payload as ChatMessage;
}

type StreamCallbacks = {
  onDelta?: (text: string) => void;
  signal?: AbortSignal;
};

/**
 * Consume SULY's SSE stream. On runtimes without ReadableStream support,
 * fall back to the same authenticated non-streaming endpoint.
 */
export async function requestAssistantReplyStream(
  conversationId: string,
  messageId: string,
  callbacks: StreamCallbacks = {},
): Promise<ChatMessage> {
  const token = await accessToken();
  const response = await fetch(apiBaseUrl + "/v1/chat/respond/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      Authorization: "Bearer " + token,
    },
    body: JSON.stringify({ conversation_id: conversationId, message_id: messageId }),
    signal: callbacks.signal,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(responseError(payload));
  }

  const reader = response.body?.getReader?.();
  if (!reader || typeof TextDecoder === "undefined") {
    if (reader) { try { await reader.cancel(); } catch { /* no streaming reader */ } }
    const message = await requestAssistantReply(conversationId, messageId, callbacks.signal);
    callbacks.onDelta?.(message.content);
    return message;
  }

  const decoder = new TextDecoder();
  let buffer = "";
  const streamState: { completed: ChatMessage | null; error: string | null } = {
    completed: null,
    error: null,
  };

  const dispatch = (frame: string) => {
    let event = "message";
    const data: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) return;
    let payload: unknown;
    try {
      payload = JSON.parse(data.join("\n"));
    } catch {
      throw new Error("وصلت بيانات غير صالحة من بث المحادثة.");
    }
    if (!payload || typeof payload !== "object") return;
    if (event === "delta") {
      const text = (payload as { text?: unknown }).text;
      if (typeof text === "string" && text) callbacks.onDelta?.(text);
    } else if (event === "complete") {
      const message = (payload as { message?: unknown }).message;
      if (message && typeof message === "object" && typeof (message as ChatMessage).id === "string") {
        streamState.completed = message as ChatMessage;
      }
    } else if (event === "error") {
      streamState.error = responseError(payload);
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        dispatch(buffer.slice(0, boundary).replace(/\r/g, ""));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) dispatch(buffer.replace(/\r/g, ""));
  } catch (error) {
    try { await reader.cancel(); } catch { /* stream already closed */ }
    throw error;
  }

  if (streamState.error) throw new Error(streamState.error);
  if (!streamState.completed) throw new Error("انقطع بث المحادثة قبل حفظ الرد. أعد المحاولة.");
  return streamState.completed;
}
