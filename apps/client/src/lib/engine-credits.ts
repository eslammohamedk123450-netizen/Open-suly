import { supabase } from "@/lib/supabase";

const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, "");

export type CreditAccount = {
  available_credits: number;
  reserved_credits: number;
  updated_at: string | null;
};

export type CreditReservation = {
  id: string | null;
  engine_id: string | null;
  reserved_credits: number;
  settled_credits: number | null;
  status: "reserved" | "settled" | "released";
  expires_at: string | null;
  created_at: string | null;
  completed_at: string | null;
};

export type CreditTransaction = {
  id: string | null;
  reservation_id: string | null;
  transaction_type: "grant" | "reserve" | "settle" | "release" | "expire";
  available_delta: number;
  reserved_delta: number;
  engine_id: string | null;
  created_at: string | null;
};

export type EngineCredits = {
  account: CreditAccount;
  reservations: CreditReservation[];
  transactions: CreditTransaction[];
};

// أرسل طلب قراءة باستخدام جلسة المستخدم؛ لا نستخدم service-role أو مفتاح محرك في العميل.
export async function getEngineCredits(): Promise<EngineCredits> {
  if (!apiBaseUrl) throw new Error("عنوان خدمة SULY API غير مضبوط بعد.");
  if (!supabase) throw new Error("اتصال الحساب غير مهيأ.");

  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session) throw new Error("سجّل الدخول لعرض رصيدك.");

  const response = await fetch(apiBaseUrl + "/v1/credits", {
    method: "GET",
    headers: { Authorization: "Bearer " + data.session.access_token },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof payload.detail === "string" ? payload.detail : "تعذر تحميل الرصيد.");
  }
  return payload as EngineCredits;
}
