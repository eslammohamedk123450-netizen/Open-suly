import { supabase } from "@/lib/supabase";

const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, "");

export type AgentMemory = {
  id: string;
  memory_key: string;
  content: string;
  tags: string[];
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!apiBaseUrl) throw new Error("عنوان خدمة SULY API غير مضبوط بعد.");
  if (!supabase) throw new Error("اتصال الحساب غير مهيأ.");
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session) throw new Error("سجّل الدخول لإدارة ذاكرة SULY.");
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
    throw new Error(typeof payload.detail === "string" ? payload.detail : "تعذر تنفيذ طلب الذاكرة.");
  }
  return payload as T;
}

export async function listAgentMemories(): Promise<AgentMemory[]> {
  const payload = await request<{ items: AgentMemory[] }>("/v1/memories");
  return payload.items ?? [];
}

export async function createAgentMemory(content: string, tags: string[] = []): Promise<AgentMemory> {
  const payload = await request<{ item: AgentMemory }>("/v1/memories", {
    method: "POST",
    body: JSON.stringify({
      memory_key: "memory-" + Date.now().toString(36),
      content: content.trim(),
      tags,
    }),
  });
  return payload.item;
}

export async function deleteAgentMemory(id: string): Promise<void> {
  await request<{ deleted: boolean }>("/v1/memories/" + encodeURIComponent(id), {
    method: "DELETE",
  });
}
