import type {
  EntryResponse,
  HabitRulesResponse,
  HistoryResponse,
  ParseResponse,
  PlanResponse,
  RemindersResponse,
  ScheduleItem,
  TaskListResponse,
} from "./types";

const API_URL = "http://localhost:8000";

const handleJson = async <T>(response: Response): Promise<T> => {
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
};

export const api = {
  parse: (text: string, today: string) =>
    fetch(`${API_URL}/parse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, today }),
    }).then((res) => handleJson<ParseResponse>(res)),
  createEntry: (text: string, today: string) =>
    fetch(`${API_URL}/entry`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, today }),
    }).then((res) => handleJson<EntryResponse>(res)),
  plan: (day: string, dayStart: string, dayEnd: string, items: ScheduleItem[]) =>
    fetch(`${API_URL}/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ day, day_start: dayStart, day_end: dayEnd, items }),
    }).then((res) => handleJson<PlanResponse>(res)),
  remindersDue: () =>
    fetch(`${API_URL}/reminders/due`).then((res) => handleJson<RemindersResponse>(res)),
  ackReminder: (id: number, action: "dismiss" | "snooze" | "done", snoozeMin?: number) =>
    fetch(`${API_URL}/reminders/${id}/ack`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, snooze_min: snoozeMin }),
    }).then((res) => handleJson<{ ok: boolean }>(res)),
  habitRules: () => fetch(`${API_URL}/habits/rules`).then((res) => handleJson<HabitRulesResponse>(res)),
  upsertHabitRule: (rule: {
    key: string;
    title: string;
    lead_min: number;
    enabled: boolean;
    default_time?: string | null;
    target_per_week?: number | null;
  }) =>
    fetch(`${API_URL}/habits/rules`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rule),
    }).then((res) => handleJson<{ id: number }>(res)),
  history: (limit = 50) =>
    fetch(`${API_URL}/history?limit=${limit}`).then((res) => handleJson<HistoryResponse>(res)),
  tasks: (filters: { from?: string; to?: string; status?: string; type?: string; q?: string }) => {
    const params = new URLSearchParams();
    if (filters.from) params.set("from", filters.from);
    if (filters.to) params.set("to", filters.to);
    if (filters.status) params.set("status", filters.status);
    if (filters.type) params.set("type", filters.type);
    if (filters.q) params.set("q", filters.q);
    return fetch(`${API_URL}/tasks?${params.toString()}`).then((res) =>
      handleJson<TaskListResponse>(res)
    );
  },
  createTask: (task: {
    title: string;
    type: "task" | "event" | "reminder";
    date?: string | null;
    start_time?: string | null;
    end_time?: string | null;
    duration_min?: number;
    priority?: number;
    location?: string | null;
    notes?: string | null;
    status?: string;
    time_pref?: string | null;
  }) =>
    fetch(`${API_URL}/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(task),
    }).then((res) => handleJson<ScheduleItem>(res)),
  updateTask: (id: number, fields: Partial<ScheduleItem>) =>
    fetch(`${API_URL}/tasks/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields),
    }).then((res) => handleJson<ScheduleItem>(res)),
  deleteTask: (id: number) =>
    fetch(`${API_URL}/tasks/${id}`, { method: "DELETE" }).then((res) => handleJson<{ ok: boolean }>(res)),
  completeTask: (id: number) =>
    fetch(`${API_URL}/tasks/${id}/complete`, { method: "POST" }).then((res) =>
      handleJson<{ ok: boolean }>(res)
    ),
};
