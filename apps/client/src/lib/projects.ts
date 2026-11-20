import { supabase } from "@/lib/supabase";

const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, "");

export type SulyProject = {
  id: string;
  user_id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!apiBaseUrl) throw new Error("خدمة SULY غير مهيأة.");
  if (!supabase) throw new Error("اتصال الحساب غير مهيأ.");
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session) throw new Error("سجّل الدخول أولًا.");
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
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "تعذر تنفيذ طلب المشاريع.");
  }
  return payload as T;
}

export async function listProjects(): Promise<SulyProject[]> {
  const result = await request<{ items: SulyProject[] }>("/v1/projects");
  return result.items ?? [];
}

export async function createProject(name: string, description = ""): Promise<SulyProject> {
  const cleanName = name.trim();
  if (!cleanName || cleanName.length > 120) throw new Error("اسم المشروع مطلوب (حتى 120 حرفًا).");
  if (description.length > 2000) throw new Error("وصف المشروع طويل جدًا.");
  return request<SulyProject>("/v1/projects", {
    method: "POST",
    body: JSON.stringify({ name: cleanName, description: description.trim() }),
  });
}

export async function updateProject(projectId: string, values: { name?: string; description?: string }): Promise<SulyProject> {
  return request<SulyProject>("/v1/projects/" + encodeURIComponent(projectId), {
    method: "PATCH",
    body: JSON.stringify(values),
  });
}

export async function deleteProject(projectId: string): Promise<void> {
  await request("/v1/projects/" + encodeURIComponent(projectId), { method: "DELETE" });
}
