import { supabase } from "@/lib/supabase";

const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, "");

export type AgentOperation = "text.analyze" | "ai.respond" | "hermes.agent.turn" | "opencode.task.run";

export type AgentTask = {
  id: string;
  title: string;
  request: string;
  status: string;
  error_code?: string | null;
  error_message?: string | null;
  result?: Record<string, unknown>;
  created_at?: string;
  manual_retry_count?: number;
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

export type AgentEngineRun = {
  id: string;
  step_id: string;
  attempt_count: number;
  engine_id: string;
  status: string;
  error_code?: string | null;
  started_at?: string;
  completed_at?: string | null;
  created_at?: string;
};

export type AgentEngineEvent = {
  id: number;
  engine_run_id: string;
  task_id: string;
  event_name: string;
  event_seq?: number | null;
  event_timestamp?: number | null;
  approval_request_id?: string | null;
  approval_choice?: "once" | "deny" | null;
  received_at: string;
};

export type AgentTaskSnapshot = {
  task: AgentTask;
  steps: AgentTaskStep[];
  engine_runs: AgentEngineRun[];
  engine_events: AgentEngineEvent[];
};

type ToolCatalogItem = {
  name: string;
  permission_scope: string;
  requires_approval: boolean;
  approved: boolean;
  available: boolean;
};

export type AgentProfile = {
  agent_id: string;
  display_name: string;
  capabilities: string[];
  enabled: boolean;
  available: boolean;
  requires_approval: boolean;
  engines: string[];
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

export async function getAgentCatalog(): Promise<AgentProfile[]> {
  const payload = await request<{ items: AgentProfile[] }>("/v1/agents");
  return payload.items ?? [];
}

export async function grantAIApproval(): Promise<void> {
  await request("/v1/tools/approvals", {
    method: "POST",
    body: JSON.stringify({ permission_scope: "ai.provider.run" }),
  });
}

export async function revokeToolApproval(permissionScope: "ai.provider.run" | "agent.hermes.run" | "engine.opencode.run"): Promise<void> {
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

export async function grantOpenCodeApproval(): Promise<void> {
  await request("/v1/tools/approvals", {
    method: "POST",
    body: JSON.stringify({ permission_scope: "engine.opencode.run" }),
  });
}

export async function createAgentTask(
  operation: AgentOperation,
  prompt: string,
  projectId?: string,
): Promise<AgentTask> {
  const cleanPrompt = prompt.trim();
  if (!cleanPrompt) throw new Error("اكتب وصف المهمة أولًا.");
  if (operation === "opencode.task.run" && !projectId) throw new Error("اربط المهمة بمشروع قبل إرسالها إلى OpenCode.");
  if (cleanPrompt.length > 20000) throw new Error("المهمة تتجاوز الحد المسموح وهو 20 ألف حرف.");
  const task = await request<AgentTask>("/v1/tasks", {
    method: "POST",
    body: JSON.stringify({
      title: operation === "opencode.task.run" ? "مهمة OpenCode برمجية" : operation === "hermes.agent.turn" ? "مهمة Hermes Agent" : operation === "ai.respond" ? "مهمة SULY AI" : "تحليل نص",
      request: operation === "text.analyze" ? "analyze: " + cleanPrompt : operation === "hermes.agent.turn" ? "agent: " + cleanPrompt : cleanPrompt,
      ...(projectId ? { project_id: projectId } : {}),
      idempotency_key: "agent-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 14),
    }),
  });
  if (operation === "opencode.task.run") {
    await request("/v1/tasks/" + encodeURIComponent(task.id) + "/opencode-plan", {
      method: "POST",
      body: "{}",
    });
  } else if (operation === "text.analyze" || operation === "hermes.agent.turn") {
    // يترك العميل اختيار العملية للخادم؛ auto-plan يتحقق من توفر الوكيل والعزل والـallow-list.
    await request("/v1/tasks/" + encodeURIComponent(task.id) + "/auto-plan", {
      method: "POST",
      body: "{}",
    });
  } else {
    const step = {
      step_key: "ai_response",
      title: "إنشاء رد عبر نموذج SULY AI",
      description: "إرسال طلب المستخدم إلى مزود الذكاء الاصطناعي المضبوط على الخادم بعد الموافقة الصريحة.",
      depends_on: [],
      input: { operation, prompt: cleanPrompt },
    };
    await request("/v1/tasks/" + encodeURIComponent(task.id) + "/plan", {
      method: "POST",
      body: JSON.stringify({ steps: [step] }),
    });
  }
  return task;
}

export async function listAgentTasks(limit = 30, projectId?: string): Promise<AgentTask[]> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (projectId) query.set("project_id", projectId);
  const payload = await request<{ items: AgentTask[] }>("/v1/tasks?" + query.toString());
  return payload.items ?? [];
}

export async function getAgentTask(taskId: string): Promise<AgentTaskSnapshot> {
  return request<AgentTaskSnapshot>("/v1/tasks/" + encodeURIComponent(taskId));
}

export type AgentApprovalDetails = {
  task_id: string;
  engine_run_id: string;
  request_id: string;
  command?: string;
  description?: string;
};

export async function getAgentApprovalDetails(
  taskId: string,
  engineRunId: string,
  requestId: string,
): Promise<AgentApprovalDetails> {
  if (!/^[A-Za-z0-9_.:@-]{1,256}$/.test(requestId)) {
    throw new Error("معرّف طلب الموافقة غير صالح.");
  }
  return request<AgentApprovalDetails>(
    "/v1/tasks/" + encodeURIComponent(taskId)
      + "/engine-runs/" + encodeURIComponent(engineRunId)
      + "/approvals/" + encodeURIComponent(requestId),
  );
}

export async function resolveAgentApproval(
  taskId: string,
  engineRunId: string,
  requestId: string,
  choice: "once" | "deny",
): Promise<{ task_id: string; engine_run_id: string; request_id: string; choice: "once" | "deny"; accepted: boolean }> {
  if (!/^[A-Za-z0-9_.:@-]{1,256}$/.test(requestId)) {
    throw new Error("معرّف طلب الموافقة غير صالح.");
  }
  return request(
    "/v1/tasks/" + encodeURIComponent(taskId)
      + "/engine-runs/" + encodeURIComponent(engineRunId) + "/approvals",
    {
      method: "POST",
      body: JSON.stringify({ request_id: requestId, choice }),
    },
  );
}

export async function steerAgentRun(
  taskId: string,
  engineRunId: string,
  input: string,
): Promise<{ task_id: string; engine_run_id: string; accepted: boolean }> {
  const cleanInput = input.trim();
  if (!cleanInput) throw new Error("اكتب التوجيه أولًا.");
  if (cleanInput.length > 20000) throw new Error("التوجيه يتجاوز الحد المسموح.");
  return request<{ task_id: string; engine_run_id: string; accepted: boolean }>(
    "/v1/tasks/" + encodeURIComponent(taskId)
      + "/engine-runs/" + encodeURIComponent(engineRunId) + "/steer",
    {
      method: "POST",
      body: JSON.stringify({ input: cleanInput }),
    },
  );
}


export async function retryAgentTask(taskId: string): Promise<{
  task_id: string;
  status: string;
  reset_steps: number;
  manual_retry_count: number;
  manual_retry_limit: number;
}> {
  return request<{
    task_id: string;
    status: string;
    reset_steps: number;
    manual_retry_count: number;
    manual_retry_limit: number;
  }>("/v1/tasks/" + encodeURIComponent(taskId) + "/retry", {
    method: "POST",
    body: "{}",
  });
}

export async function cancelAgentTask(taskId: string): Promise<AgentTask> {
  return request<AgentTask>("/v1/tasks/" + encodeURIComponent(taskId) + "/cancel", {
    method: "POST",
    body: "{}",
  });
}
