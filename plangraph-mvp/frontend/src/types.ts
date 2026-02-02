export type ScheduleItem = {
  id?: number | null;
  title: string;
  type: "event" | "task" | "reminder";
  date: string | null;
  start_time: string | null;
  end_time: string | null;
  duration_min: number;
  priority: number;
  location: string | null;
  notes: string | null;
  status?: string;
  time_pref?: string | null;
  placement_hint?: string | null;
  created_at?: string | null;
};

export type PlannedItem = ScheduleItem & {
  planned_start: string | null;
  planned_end: string | null;
  status: string;
  reason: string | null;
};

export type ParseResponse = {
  items: ScheduleItem[];
};

export type EntryResponse = {
  entry_id: number;
  items: ScheduleItem[];
};

export type PlanResponse = {
  day: string;
  planned: PlannedItem[];
  conflicts: string[];
};

export type Reminder = {
  id: number;
  due_at: string;
  kind: string;
  title: string;
  body: string | null;
  status: string;
  reason: string | null;
  related_item_title?: string | null;
  context?: string | null;
};

export type RemindersResponse = {
  now: string;
  reminders: Reminder[];
};

export type NowResponse = {
  now: string;
  message?: string | null;
  due_reminders: Reminder[];
  next_items: PlannedItem[];
  later_today: PlannedItem[];
};

export type HabitRule = {
  id: number;
  key: string;
  title: string;
  lead_min: number;
  enabled: boolean;
  default_time: string | null;
  target_per_week: number | null;
  typical_time: string | null;
};

export type HabitRulesResponse = {
  rules: HabitRule[];
};

export type HistoryEntry = {
  id: number;
  text: string;
  today: string | null;
  created_at: string;
  item_count: number;
};

export type HistoryPlan = {
  id: number;
  day: string;
  day_start: string;
  day_end: string;
  created_at: string;
  planned_count: number;
  unscheduled_count: number;
};

export type HistoryResponse = {
  entries: HistoryEntry[];
  plans: HistoryPlan[];
};

export type TaskListResponse = {
  items: PlannedItem[];
};
