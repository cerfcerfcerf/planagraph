import type { InsightsResponse, NowResponse, ParsedItem, Settings, Task } from "./types";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Request failed");
  }
  return response.json() as Promise<T>;
}

export const api = {
  parsePlan: (text: string) =>
    request<{ items: ParsedItem[] }>("/parse", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  listTasks: () => request<{ items: Task[] }>("/tasks"),
  createTask: (task: Partial<Task>) =>
    request<Task>("/tasks", {
      method: "POST",
      body: JSON.stringify(task),
    }),
  updateTask: (id: number, task: Partial<Task>) =>
    request<Task>(`/tasks/${id}`, {
      method: "PATCH",
      body: JSON.stringify(task),
    }),
  getSettings: () => request<Settings>("/settings"),
  updateSettings: (settings: Settings) =>
    request<Settings>("/settings", {
      method: "POST",
      body: JSON.stringify(settings),
    }),
  getNow: () => request<NowResponse>("/now"),
  reminderAction: (id: number, action: string) =>
    request<{ ok: boolean }>(`/reminders/${id}/action`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
  getInsights: () => request<InsightsResponse>("/insights"),
};
