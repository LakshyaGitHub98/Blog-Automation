export type PostStatus = "queued" | "generating" | "completed" | "failed";

export interface Post {
  id: string;
  topic: string;
  title: string;
  status: PostStatus;
  stage: string;
  iterations_used: number;
  final_score: number | null;
  detector: string;
  error: string;
  created_at: string;
  content: string;
}

export interface Revision {
  id: string;
  iteration: number;
  ai_score: number | null;
  detector: string;
  content: string;
}

export interface PostDetail {
  post: Post;
  revisions: Revision[];
}

export interface JobStatus {
  request_id: string;
  status: PostStatus;
  stage: string;
  error: string;
  title: string;
  final_score: number | null;
  iterations_used: number;
  detector: string;
  elapsed_seconds: number | null;
}

export interface GenerateResponse {
  request_id: string;
  status: string;
  async: boolean;
}

export interface GenerateOptions {
  topic: string;
  max_iterations?: number;
  temperature?: number;
  max_tokens?: number;
}

export interface Health {
  status: string;
  mode: string;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: init?.body
      ? { "Content-Type": "application/json", ...init.headers }
      : init?.headers,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message =
      (data as { detail?: string }).detail ?? `Request failed (${res.status})`;
    throw new Error(message);
  }
  return data as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  generate: (body: GenerateOptions) =>
    request<GenerateResponse>("/api/generate", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  status: (id: string) => request<JobStatus>(`/api/status/${id}`),
  posts: () => request<{ posts: Post[] }>("/api/posts"),
  post: (id: string) => request<PostDetail>(`/api/posts/${id}`),
};
