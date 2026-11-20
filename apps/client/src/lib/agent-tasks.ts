import { supabase } from "@/lib/supabase";

const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, "");

export type AgentOperation = "text.analyze" | "ai.respond" | "hermes.agent.turn";

export type AgentTask = {
  id: string;
  title: string;
  request: string;
  status: string;
  error_code?: string | null;
  error_message?: string | null;
  result?: Record<string, unknown>;
};

export type AgentTaskStep = {
  id: string;
  step_key: string;
  title: string;
  status: string;
  output?: Record<string, unknown>;
  error_code?: string | null;
  error_message?: string | null;
  attempt_count: number;
  max_attempts: number;
};

export type AgentTaskSnapshot = {
  task: AgentTask;
  steps: AgentTaskStep[];
};

type ToolCatalogItem = {
  name: string;
  permission_scope: string;
  requires_approval: boolean;
  approved: boolean;
  available: boolean;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!apiBaseUrl) throw new Error("عنوان خدمة SULY API غير مضبوط بعد. أضف EXPO_PUBLIC_API_BASE_URL إلى إعدادات التطبيق.");
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
    const detail = payload && typeof payload.detail === "string" ? payload.detail : "تعذر تنفيذ طلب الوكيل.";
    throw new Error(detail);
  }
  return payload as T;
}

export async function getAgentToolCatalog(): Promise<ToolCatalogItem[]> {
  const payload = await request<{ items: ToolCatalogItem[] }>("/v1/tools/approvals/catalog");
  return payload.items ?? [];
}

export async function grantAIApproval(): Promise<void> {
  await request("/v1/tools/approvals", {
    method: "POST",
    body: JSON.stringify({ permission_scope: "ai.provider.run" }),
  });
}

export async function revokeToolApproval(permissionScope: "ai.provider.run" | "agent.hermes.run"): Promise<void> {
  await request("/v1/tools/approvals", {
    method: "DELETE",
    body: JSON.stringify({ permission_scope: permissionScope }),
  });
}

export async function grantHermesApproval(): Promise<void> {
  await request("/v1/tools/approvals", {
    method: "POST",
    body: JSON.stringify({ permission_scope: "agent.hermes.run" }),
  });
}

export async function createAgentTask(
  operation: AgentOperation,
  prompt: string,
): Promise<AgentTask> {
  const cleanPrompt = prompt.trim();
  if (!cleanPrompt) throw new Error("اكتب وصف المهمة أولًا.");
  if (cleanPrompt.length > 20000) throw new Error("المهمة تتجاوز الحد المسموح وهو 20 ألف حرف.");
  const task = await request<AgentTask>("/v1/tasks", {
    method: "POST",
    body: JSON.stringify({
      title: operation === "hermes.agent.turn" ? "مهمة Hermes Agent" : operation === "ai.respond" ? "مهمة SULY AI" : "تحليل نص",
      request: cleanPrompt,
      idempotency_key: "agent-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 14),
    }),
  });
  const step = operation === "text.analyze"
    ? {
        step_key: "analyze_text",
        title: "تحليل النص",
        description: "تحليل محلي حتمي للنص وإرجاع عدد الكلمات والحروف والأسطر.",
        depends_on: [],
        input: { operation, text: cleanPrompt },
      }
    : operation === "ai.respond"
      ? {
          step_key: "ai_response",
          title: "إنشاء رد عبر نموذج SULY AI",
          description: "إرسال طلب المستخدم إلى مزود الذكاء الاصطناعي المضبوط على الخادم بعد الموافقة الصريحة.",
          depends_on: [],
          input: { operation, prompt: cleanPrompt },
        }
      : {
        step_key: "hermes_turn",
        title: "تنفيذ مهمة Hermes Agent",
        description: "تشغيل طلب المستخدم عبر Hermes بعد التحقق من موافقته وحدود التنفيذ.",
        depends_on: [],
        input: { operation, prompt: cleanPrompt },
      };
  await request("/v1/tasks/" + encodeURIComponent(task.id) + "/plan", {
    method: "POST",
    body: JSON.stringify({ steps: [step] }),
  });
  return task;
}

export async function getAgentTask(taskId: string): Promise<AgentTaskSnapshot> {
  return request<AgentTaskSnapshot>("/v1/tasks/" + encodeURIComponent(taskId));
}

export async function cancelAgentTask(taskId: string): Promise<AgentTask> {
  return request<AgentTask>("/v1/tasks/" + encodeURIComponent(taskId) + "/cancel", {
    method: "POST",
    body: "{}",
  });
}
