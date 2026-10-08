import { t } from "../i18n/uk";

export type User = {
  id: number;
  email: string;
  timezone: string;
  telegram_linked: boolean;
  telegram_username: string | null;
  telegram_blocked: boolean;
  created_at: string;
};

export type TopicQuery = {
  id: number;
  query: string;
  source: "google_news" | "tavily";
  language: string;
};

export type TopicQueryInput = Omit<TopicQuery, "id">;

export type Frequency = "hourly" | "6h" | "daily" | "weekly";

export type Topic = {
  id: number;
  name: string;
  description: string;
  language: string;
  frequency: Frequency;
  send_hour: number;
  weekday: number;
  is_active: boolean;
  relevance_threshold: number;
  last_run_at: string | null;
  next_run_at: string | null;
  last_run_status: string | null;
  created_at: string;
  queries: TopicQuery[];
  digest_count: number;
};

export type TopicInput = {
  name: string;
  description: string;
  language: string;
  frequency: Frequency;
  send_hour: number;
  weekday: number;
  relevance_threshold?: number | null;
  is_active?: boolean;
};

export type Digest = {
  id: number;
  topic_id: number;
  created_at: string;
  sent_at: string | null;
  status: string;
  content_markdown: string;
  article_count: number;
  error: string | null;
};

export type Meta = {
  bot_username: string;
  languages: Record<string, string>;
  frequencies: Frequency[];
  max_topics_per_user: number;
  default_relevance_threshold: number;
  fake_llm: boolean;
  fake_tavily: boolean;
  fake_telegram: boolean;
};

export type TelegramLink = { url: string; token: string; expires_at: string };

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

let csrfToken: string | null = null;

function readCookie(name: string): string | null {
  const match = document.cookie.split("; ").find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
}

async function ensureCsrf(): Promise<string> {
  const fromCookie = readCookie("nd_csrf");
  if (fromCookie) return fromCookie;
  if (csrfToken) return csrfToken;
  const resp = await fetch("/api/auth/csrf", { credentials: "same-origin" });
  const data = (await resp.json()) as { csrf_token: string };
  csrfToken = data.csrf_token;
  return csrfToken;
}

function messageFor(status: number, code: string): string {
  if (t.apiErrors[code]) return t.apiErrors[code];
  if (status === 422) return t.apiErrors.validation;
  if (status === 404) return t.apiErrors.not_found;
  return t.common.unknownError;
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = await ensureCsrf();

  let resp: Response;
  try {
    resp = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network", t.common.networkError);
  }

  if (resp.status === 204) return undefined as T;
  const data = await resp.json().catch(() => null);
  if (!resp.ok) {
    const detail = data?.detail;
    const code = typeof detail === "string" ? detail : resp.status === 422 ? "validation" : "error";
    if (code === "csrf_failed") csrfToken = null;
    throw new ApiError(resp.status, code, messageFor(resp.status, code));
  }
  return data as T;
}

export const api = {
  meta: () => request<Meta>("GET", "/api/meta"),
  me: () => request<User>("GET", "/api/auth/me"),
  login: (email: string, password: string) =>
    request<User>("POST", "/api/auth/login", { email, password }),
  register: (email: string, password: string, timezone?: string) =>
    request<User>("POST", "/api/auth/register", { email, password, timezone }),
  logout: () => request<void>("POST", "/api/auth/logout"),
  updateMe: (timezone: string) => request<User>("PATCH", "/api/me", { timezone }),

  topics: () => request<Topic[]>("GET", "/api/topics"),
  topic: (id: number) => request<Topic>("GET", `/api/topics/${id}`),
  createTopic: (input: TopicInput) => request<Topic>("POST", "/api/topics", input),
  updateTopic: (id: number, input: Partial<TopicInput>) =>
    request<Topic>("PATCH", `/api/topics/${id}`, input),
  deleteTopic: (id: number) => request<void>("DELETE", `/api/topics/${id}`),
  replaceQueries: (id: number, queries: TopicQueryInput[]) =>
    request<Topic>("PUT", `/api/topics/${id}/queries`, queries),
  regenerateQueries: (id: number) => request<Topic>("POST", `/api/topics/${id}/queries/regenerate`),
  runTopic: (id: number) =>
    request<{ job_id: string; enqueued: boolean }>("POST", `/api/topics/${id}/run`),
  digests: (id: number) => request<Digest[]>("GET", `/api/topics/${id}/digests`),

  telegramLink: () => request<TelegramLink>("POST", "/api/telegram/link"),
  telegramUnlink: () => request<void>("POST", "/api/telegram/unlink"),
};
