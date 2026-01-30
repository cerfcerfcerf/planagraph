export type ScheduleItem = {
  title: string;
  type: "event" | "task" | "reminder";
  date: string | null;
  start_time: string | null;
  end_time: string | null;
  duration_min: number;
  priority: number;
  location: string | null;
  notes: string | null;
};

export type PlannedItem = ScheduleItem & {
  planned_start: string | null;
  planned_end: string | null;
  status: string;
  reason: string | null;
};
