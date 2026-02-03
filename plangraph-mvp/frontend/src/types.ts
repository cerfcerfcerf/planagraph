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

export type ParseResponse = {
  items: ParsedItem[];
};

export type Task = {
  id: number;
  title: string;
  notes: string | null;
  due_at: string | null;
  window_start: string | null;
  window_end: string | null;
  priority: string;
  status: string;
  recurrence: string | null;
  recurrence_detail: string | null;
  created_at: string;
  updated_at: string;
};

export type Settings = {
  policy_mode: "baseline" | "adaptive";
  daily_budget: number;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  lead_time_min: number;
};

export type Reminder = {
  id: number;
  task_id: number;
  title: string;
  scheduled_for: string;
  state: string;
};

export type NowResponse = {
  next_best_action: Reminder | null;
  next_6_hours: Reminder[];
  later_today: Reminder[];
  why_now: string;
};

export type InsightPoint = {
  date: string;
  value: number;
};

export type Insights = {
  notifications_per_day: InsightPoint[];
  completions_per_day: InsightPoint[];
  notifications_per_completion: InsightPoint[];
  missed_rate_proxy: InsightPoint[];
};
