import type {
  InsightsResponse,
  InsightsSummary,
  NowResponse,
  ParseItem,
  Settings,
  Task,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    ...options,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

export function parsePlan(text: string): Promise<{ items: ParseItem[] }> {
  return request("/parse", { method: "POST", body: JSON.stringify({ text }) });
}

export function createTasks(tasks: Omit<Task, "id" | "status" | "created_at" | "updated_at">[]) {
  return request<{ tasks: Task[] }>("/tasks", {
    method: "POST",
    body: JSON.stringify(tasks),
  });
}

export function listTasks(): Promise<{ tasks: Task[] }> {
  return request("/tasks");
}

export function updateTask(id: number, payload: Partial<Task>): Promise<Task> {
  return request(`/tasks/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function fetchSettings(): Promise<Settings> {
  return request("/settings");
}

export function updateSettings(payload: Partial<Settings>): Promise<Settings> {
  return request("/settings", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchNow(): Promise<NowResponse> {
  return request("/now");
}

export function reminderAction(id: number, action: string) {
  return request(`/reminders/${id}/action`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export function fetchInsights(): Promise<InsightsResponse> {
  return request("/insights");
}

export function fetchInsightsSummary(): Promise<InsightsSummary> {
  return request("/insights/summary");
}

export function fetchConfig(): Promise<{ use_llm: boolean }> {
  return request("/config");
}
