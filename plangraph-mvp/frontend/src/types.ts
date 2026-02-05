export type ParsedItem = {
  title: string;
  date: string | null;
  due_time: string | null;
  window_start: string | null;
  window_end: string | null;
  priority: "low" | "med" | "high";
  recurrence: "none" | "daily" | "weekly" | "every_2_days" | "custom";
  recurrence_detail: string | null;
  confidence: number;
  notes: string | null;
};

export type Task = {
  id: number;
  title: string;
  notes: string | null;
  due_at: string | null;
  window_start: string | null;
  window_end: string | null;
  priority: "low" | "med" | "high";
  status: "active" | "completed" | "archived";
  recurrence: string | null;
  created_at: string;
  updated_at: string;
};

export type Settings = {
  policy_mode: "baseline" | "adaptive";
  daily_budget: number;
  quiet_hours_start: string;
  quiet_hours_end: string;
  lead_time_min: number;
};

export type NowItem = {
  task_id: number;
  title: string;
  due_at: string | null;
  window_start: string | null;
  window_end: string | null;
  priority: string;
};

export type NowResponse = {
  next_best_action: NowItem | null;
  next_reminder_id: number | null;
  why_now: string;
  next_6_hours: NowItem[];
  later_today: NowItem[];
};

export type InsightsSeriesPoint = {
  date: string;
  count: number;
};

export type InsightsResponse = {
  notifications_per_day: InsightsSeriesPoint[];
  completions_per_day: InsightsSeriesPoint[];
  missed_rate_proxy: number;
  notifications_per_completion: number;
  totals: Record<string, number>;
};
