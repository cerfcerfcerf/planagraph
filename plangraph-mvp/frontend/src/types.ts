export type ParseItem = {
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
  recurrence_suggestions?: RecurrenceSuggestion[] | null;
  task_type?: string | null;
};

export type Task = {
  id: number;
  title: string;
  notes: string | null;
  due_at: string | null;
  window_start: string | null;
  window_end: string | null;
  priority: "low" | "med" | "high";
  task_type: "meal" | "sleep" | "medication" | "hygiene" | "class" | "exercise" | "other";
  status: "active" | "completed" | "archived";
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
  lead_time_minutes: number;
};

export type Reminder = {
  id: number;
  task_id: number;
  scheduled_for: string;
  state: string;
  title?: string | null;
  why_now?: WhyNow | null;
};

export type WhyNow = {
  reasons: string[];
  score: number;
};

export type NowAction = {
  reminder_id: number | null;
  task_id: number | null;
  title: string;
  scheduled_for: string | null;
  window_start: string | null;
  window_end: string | null;
  priority: string;
  why_now: WhyNow;
};

export type NowResponse = {
  next_best_action: NowAction | null;
  next_6_hours: Reminder[];
  later_today: Reminder[];
};

export type InsightsResponse = {
  notifications_per_day: { date: string; value: number }[];
  completions_per_day: { date: string; value: number }[];
  missed_rate_proxy: { date: string; value: number }[];
  notifications_per_completion: { date: string; value: number }[];
  stale_reminder_rate: { date: string; value: number }[];
  median_completion_delay: { date: string; value: number }[];
};

export type InsightsSummary = {
  narrative: string;
  recommendations: string[];
  metrics: {
    completion_rate: number;
    notifications_per_day: number;
    notifications_per_completion: number;
    missed_rate_proxy: number;
    stale_reminder_rate: number;
    median_completion_delay: number;
  };
};

export type Template = {
  id: number;
  title: string;
  default_duration_min: number;
  default_type: "meal" | "sleep" | "medication" | "hygiene" | "class" | "exercise" | "other";
  default_priority: "low" | "med" | "high";
  pinned: boolean;
  used_count: number;
  last_used: string | null;
};

export type TemplateCreate = {
  title: string;
  default_duration_min?: number;
  default_type?: "meal" | "sleep" | "medication" | "hygiene" | "class" | "exercise" | "other";
  default_priority?: "low" | "med" | "high";
  pinned?: boolean;
};

export type RecurrenceSuggestion = {
  recurrence: "daily" | "weekly" | "every_2_days" | "custom" | "none";
  recurrence_detail: string | null;
  confidence: number;
};

export type ParsedItemWithSuggestions = ParseItem & {
  recurrence_suggestions?: RecurrenceSuggestion[] | null;
  task_type?: string | null;
};
