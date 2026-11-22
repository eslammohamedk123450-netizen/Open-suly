import { supabase } from "@/lib/supabase";

const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, "");

export type ProjectFile = {
  id: string;
  path: string;
  size: number;
  updated_at: string;
};

export type ProjectFileContent = ProjectFile & { content: string };

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
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "تعذر تنفيذ طلب ملفات المشروع.");
  }
  return payload as T;
}

export async function listProjectFiles(projectId: string): Promise<ProjectFile[]> {
  const result = await request<{ items: ProjectFile[] }>(
    "/v1/projects/" + encodeURIComponent(projectId) + "/files",
  );
  return result.items ?? [];
}

export async function readProjectFile(projectId: string, path: string): Promise<ProjectFileContent> {
  return request<ProjectFileContent>(
    "/v1/projects/" + encodeURIComponent(projectId) + "/file?path=" + encodeURIComponent(path),
  );
}

export async function saveProjectFile(projectId: string, path: string, content: string, expectedUpdatedAt: string | null): Promise<ProjectFile> {
  if (new TextEncoder().encode(content).byteLength > 256 * 1024) {
    throw new Error("الحد الأقصى لحجم الملف 256 كيلوبايت.");
  }
  return request<ProjectFile>(
    "/v1/projects/" + encodeURIComponent(projectId) + "/file?path=" + encodeURIComponent(path),
    { method: "PUT", body: JSON.stringify({ content, expected_updated_at: expectedUpdatedAt }) },
  );
}

export async function deleteProjectFile(projectId: string, path: string): Promise<void> {
  await request(
    "/v1/projects/" + encodeURIComponent(projectId) + "/file?path=" + encodeURIComponent(path),
    { method: "DELETE" },
  );
}

export type ProjectFileRevision = {
  id: string;
  path: string;
  size_bytes: number;
  created_at: string;
};

export type ProjectFileRevisionContent = ProjectFileRevision & { content: string };

export async function listProjectFileHistory(projectId: string, filePath: string): Promise<ProjectFileRevision[]> {
  const result = await request<{ items: ProjectFileRevision[] }>(
    "/v1/projects/" + encodeURIComponent(projectId) + "/file/history?path=" + encodeURIComponent(filePath),
  );
  return result.items ?? [];
}

export async function readProjectFileRevision(projectId: string, revisionId: string): Promise<ProjectFileRevisionContent> {
  return request<ProjectFileRevisionContent>(
    "/v1/projects/" + encodeURIComponent(projectId) + "/file/history/" + encodeURIComponent(revisionId),
  );
}

export async function restoreProjectFileRevision(projectId: string, revisionId: string, expectedUpdatedAt: string): Promise<{ restored: boolean; path: string; updated_at: string }> {
  return request(
    "/v1/projects/" + encodeURIComponent(projectId) + "/file/history/" + encodeURIComponent(revisionId) + "/restore",
    { method: "POST", body: JSON.stringify({ expected_updated_at: expectedUpdatedAt }) },
  );
}


export type ProjectFileDiffPreview = {
  path: string;
  has_changes: boolean;
  base_updated_at: string | null;
  diff: string;
};

export async function previewProjectFile(
  projectId: string,
  path: string,
  content: string,
  expectedUpdatedAt: string | null,
): Promise<ProjectFileDiffPreview> {
  if (new TextEncoder().encode(content).byteLength > 256 * 1024) {
    throw new Error("الحد الأقصى لحجم الملف 256 كيلوبايت.");
  }
  return request(
    "/v1/projects/" + encodeURIComponent(projectId) + "/file/preview?path=" + encodeURIComponent(path),
    { method: "POST", body: JSON.stringify({ content, expected_updated_at: expectedUpdatedAt }) },
  );
}


export type ProjectFileSearchResult = {
  path: string;
  snippet: string;
  updated_at: string | null;
};

export async function searchProjectFiles(
  projectId: string,
  query: string,
  limit = 20,
): Promise<ProjectFileSearchResult[]> {
  const cleanQuery = query.trim();
  if (cleanQuery.length < 2 || cleanQuery.length > 120) {
    throw new Error("اكتب كلمتين على الأقل للبحث داخل ملفات المشروع.");
  }
  const boundedLimit = Math.max(1, Math.min(20, Math.floor(limit)));
  const params = new URLSearchParams({ q: cleanQuery, limit: String(boundedLimit) });
  const result = await request<{ items: ProjectFileSearchResult[] }>(
    "/v1/projects/" + encodeURIComponent(projectId) + "/files/search?" + params.toString(),
  );
  return result.items ?? [];
}
