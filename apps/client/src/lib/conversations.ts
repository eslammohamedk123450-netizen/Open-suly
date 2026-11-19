import type { SupabaseClient } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";

export type Conversation = {
  id: string;
  user_id: string;
  title: string;
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

function getClient(): SupabaseClient {
  if (!supabase) throw new Error("اتصال SULY بقاعدة البيانات غير مهيأ.");
  return supabase;
}

async function getCurrentUserId(client: SupabaseClient): Promise<string> {
  const { data, error } = await client.auth.getUser();
  if (error || !data.user) throw new Error("يجب تسجيل الدخول أولًا.");
  return data.user.id;
}

export async function listConversations(): Promise<Conversation[]> {
  const client = getClient();
  const { data, error } = await client.from("conversations").select("*").order("updated_at", { ascending: false });
  if (error) throw error;
  return (data ?? []) as Conversation[];
}

export async function createConversation(title = "محادثة جديدة"): Promise<Conversation> {
  const client = getClient();
  const userId = await getCurrentUserId(client);
  const { data, error } = await client.from("conversations").insert({ user_id: userId, title: title.trim() || "محادثة جديدة" }).select("*").single();
  if (error) throw error;
  return data as Conversation;
}

export async function listMessages(conversationId: string): Promise<ChatMessage[]> {
  const client = getClient();
  const { data, error } = await client.from("messages").select("*").eq("conversation_id", conversationId).order("created_at", { ascending: true }).order("id", { ascending: true });
  if (error) throw error;
  return (data ?? []) as ChatMessage[];
}

export async function sendUserMessage(conversationId: string, content: string): Promise<ChatMessage> {
  const cleanContent = content.trim();
  if (!cleanContent) throw new Error("اكتب رسالة قبل الإرسال.");
  if (cleanContent.length > 100000) throw new Error("الرسالة أطول من الحد المسموح.");
  const client = getClient();
  const userId = await getCurrentUserId(client);
  const { data, error } = await client.from("messages").insert({
    conversation_id: conversationId,
    user_id: userId,
    content: cleanContent,
  }).select("*").single();
  if (error) throw error;
  return data as ChatMessage;
}

export async function renameConversation(conversationId: string, title: string): Promise<Conversation> {
  const cleanTitle = title.trim();
  if (!cleanTitle || cleanTitle.length > 200) throw new Error("عنوان المحادثة يجب أن يكون بين حرف واحد و200 حرف.");
  const client = getClient();
  const { data, error } = await client.from("conversations").update({ title: cleanTitle }).eq("id", conversationId).select("*").single();
  if (error) throw error;
  return data as Conversation;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const client = getClient();
  const { error } = await client.from("conversations").delete().eq("id", conversationId);
  if (error) throw error;
}
