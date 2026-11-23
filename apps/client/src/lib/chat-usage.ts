import { supabase } from "@/lib/supabase";

const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, "");

export type ChatUsageSummary = {
  scope: "chat";
  coverage: "all_assistant_messages" | "latest_500_assistant_messages";
  assistant_messages_checked: number;
  usage_records: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  truncated: boolean;
  sample_limit: number;
  period_start: string | null;
  period_end: string | null;
};

// Counts are provider-reported and owner-scoped; the client never sees message metadata.
export async function getChatUsageSummary(): Promise<ChatUsageSummary> {
  if (!apiBaseUrl) throw new Error("عنوان خدمة SULY API غير مضبوط بعد.");
  if (!supabase) throw new Error("اتصال الحساب غير مهيأ.");

  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session) throw new Error("سجّل الدخول لعرض استهلاك المحادثات.");

  const response = await fetch(apiBaseUrl + "/v1/usage/chat", {
    method: "GET",
    headers: { Authorization: "Bearer " + data.session.access_token },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof payload.detail === "string" ? payload.detail : "تعذر تحميل استهلاك المحادثات.");
  }
  return payload as ChatUsageSummary;
}
