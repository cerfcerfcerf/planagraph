import type {
  EntryResponse,
  HabitRulesResponse,
  HistoryResponse,
  ParseResponse,
  PlanResponse,
  RemindersResponse,
  ScheduleItem,
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
};
