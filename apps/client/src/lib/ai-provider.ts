import { supabase } from "@/lib/supabase";

const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, "");

export type AIProviderStatus = {
  configured: boolean;
  source: "vault" | "environment" | "none";
  provider: string | null;
  base_url: string | null;
  model: string | null;
  api_key_set: boolean;
};

function secureApiBaseUrl(): string {
  if (!apiBaseUrl) throw new Error("عنوان خدمة SULY API غير مضبوط بعد.");
  try {
    if (new URL(apiBaseUrl).protocol === "https:") return apiBaseUrl;
  } catch {
    // A malformed API origin is treated the same as an insecure one.
  }
  throw new Error("يجب استخدام اتصال HTTPS آمن قبل إدارة إعدادات الذكاء الاصطناعي.");
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const secureBaseUrl = secureApiBaseUrl();
  if (!supabase) throw new Error("اتصال الحساب غير مهيأ.");
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session) throw new Error("انتهت جلسة الدخول. سجّل الدخول مرة أخرى.");

  const response = await fetch(secureBaseUrl + path, {
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
      : "تعذر تحديث إعداد مزود AI.";
    throw new Error(detail);
  }
  return payload as T;
}

export function getAIProviderStatus(): Promise<AIProviderStatus> {
  return request<AIProviderStatus>("/v1/owner/ai-provider");
}

export function saveAIProviderConfig(input: {
  provider: "openai-compatible";
  base_url: string;
  model: string;
  api_key: string;
}): Promise<AIProviderStatus> {
  return request<AIProviderStatus>("/v1/owner/ai-provider", {
    method: "PUT",
    body: JSON.stringify(input),
  });
}


/** احذف إعداد Vault مع إرجاع حالة أي إعداد خادمي احتياطي. */
export function clearAIProviderConfig(): Promise<AIProviderStatus> {
  return request<AIProviderStatus>("/v1/owner/ai-provider", {
    method: "DELETE",
  });
}
