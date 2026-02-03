import type { Insights, NowResponse, ParseResponse, Reminder, Settings, Task } from "./types";

const API_URL = "http://localhost:8000";

const handleJson = async <T>(response: Response): Promise<T> => {
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
};

export const api = {
  parse: (text: string) =>
    fetch(`${API_URL}/parse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).then((res) => handleJson<ParseResponse>(res)),
  tasks: () => fetch(`${API_URL}/tasks`).then((res) => handleJson<Task[]>(res)),
  createTask: (payload: {
    title: string;
    notes?: string | null;
    date?: string | null;
    due_time?: string | null;
    window_start?: string | null;
    window_end?: string | null;
    priority?: "low" | "med" | "high";
    recurrence?: "none" | "daily" | "weekly" | "every_2_days" | "custom";
    recurrence_detail?: string | null;
  }) =>
    fetch(`${API_URL}/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((res) => handleJson<Task>(res)),
  updateTask: (id: number, payload: Partial<Task>) =>
    fetch(`${API_URL}/tasks/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((res) => handleJson<Task>(res)),
  settings: () => fetch(`${API_URL}/settings`).then((res) => handleJson<Settings>(res)),
  updateSettings: (payload: Partial<Settings>) =>
    fetch(`${API_URL}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((res) => handleJson<Settings>(res)),
  now: () => fetch(`${API_URL}/now`).then((res) => handleJson<NowResponse>(res)),
  reminderAction: (id: number, action: "done" | "snooze_10" | "snooze_30" | "dismiss") =>
    fetch(`${API_URL}/reminders/${id}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    }).then((res) => handleJson<Reminder>(res)),
  insights: () => fetch(`${API_URL}/insights`).then((res) => handleJson<Insights>(res)),
  seed: () => fetch(`${API_URL}/seed`, { method: "POST" }).then((res) => handleJson<{ status: string }>(res)),
};
