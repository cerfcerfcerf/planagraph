import { useEffect, useMemo, useRef, useState } from "react";
import {
  createTasks,
  createTemplate,
  fetchConfig,
  fetchInsights,
  fetchInsightsSummary,
  fetchLazySuggestions,
  fetchNow,
  fetchSettings,
  fetchTemplates,
  listTasks,
  parsePlan,
  reminderAction,
  updateSettings,
  updateTask,
} from "./api";
import type {
  InsightsResponse,
  InsightsSummary,
  NowResponse,
  ParseItem,
  Settings,
  Task,
  Template,
  WhyNow,
} from "./types";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { format, parseISO } from "date-fns";

const pages = ["Now", "Add", "Tasks", "Policy", "Insights"] as const;

type Page = (typeof pages)[number];

function combineDateTime(dateValue: string | null, timeValue: string | null) {
  if (!dateValue || !timeValue) return null;
  return new Date(`${dateValue}T${timeValue}:00`).toISOString();
}

function formatTaskTime(task: Task) {
  if (task.due_at) {
    return format(parseISO(task.due_at), "EEE, MMM d · HH:mm");
  }
  if (task.window_start && task.window_end) {
    const start = parseISO(task.window_start);
    const end = parseISO(task.window_end);
    const today = new Date().toISOString().slice(0, 10);
    if (task.window_start.slice(0, 10) === task.window_end.slice(0, 10)) {
      const timeLabel = `${format(start, "HH:mm")}–${format(end, "HH:mm")}`;
      if (task.window_start.slice(0, 10) === today) {
        return timeLabel;
      }
      const dateLabel = format(start, "EEE, MMM d");
      return `${dateLabel} · ${timeLabel} (flexible)`;
    }
    const startLabel = format(start, "EEE, MMM d · HH:mm");
    const endLabel = format(end, "EEE, MMM d · HH:mm");
    return `${startLabel} – ${endLabel} (flexible)`;
  }
  return "Flexible";
}

function formatReminderTime(value: string | null) {
  if (!value) return "Flexible";
  return format(parseISO(value), "EEE, MMM d · HH:mm");
}

export default function App() {
  const [page, setPage] = useState<Page>("Now");
  const [parseText, setParseText] = useState("");
  const [parsedItems, setParsedItems] = useState<ParseItem[]>([]);
  const [isParsing, setIsParsing] = useState(false);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskSearch, setTaskSearch] = useState("");
  const [laterOpen, setLaterOpen] = useState(true);
  const [tasksOpen, setTasksOpen] = useState({
    today: true,
    tomorrow: true,
    later: true,
    completed: false,
  });
  const [settings, setSettings] = useState<Settings | null>(null);
  const [now, setNow] = useState<NowResponse | null>(null);
  const [insights, setInsights] = useState<InsightsResponse | null>(null);
  const [summary, setSummary] = useState<InsightsSummary | null>(null);
  const [useLlm, setUseLlm] = useState(false);
  const [quickAddOpen, setQuickAddOpen] = useState(false);
  const [quickAddText, setQuickAddText] = useState("");
  const [isDictating, setIsDictating] = useState(false);
  const [lazyTask, setLazyTask] = useState<Task | null>(null);
  const [lazySuggestion, setLazySuggestion] = useState<string[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [quickAddDraft, setQuickAddDraft] = useState<ParseItem | null>(null);
  const [quickAddSource, setQuickAddSource] = useState<{ type: "template" | "recent"; id: number } | null>(
    null
  );
  const [quickAddSubmitting, setQuickAddSubmitting] = useState(false);
  const [reminderSubmitting, setReminderSubmitting] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [editDraft, setEditDraft] = useState<{
    title: string;
    date: string;
    startTime: string;
    endTime: string;
    priority: ParseItem["priority"];
    recurrence: ParseItem["recurrence"];
  } | null>(null);
  const notifiedIds = useRef(new Set<number>());

  const refreshTasks = () => listTasks().then((data) => setTasks(data.tasks));

  const refreshSettings = () => fetchSettings().then(setSettings);

  const refreshNow = () => fetchNow().then(setNow);

  const refreshInsights = () => fetchInsights().then(setInsights);

  const refreshSummary = () => fetchInsightsSummary().then(setSummary);

  const refreshConfig = () => fetchConfig().then((data) => setUseLlm(data.use_llm));

  const refreshTemplates = () => fetchTemplates().then(setTemplates);

  function showToast(message: string) {
    setToastMessage(message);
    window.setTimeout(() => setToastMessage(null), 4000);
  }

  useEffect(() => {
    refreshTasks();
    refreshSettings();
    refreshNow();
    refreshInsights();
    refreshSummary();
    refreshConfig();
    refreshTemplates();
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      refreshNow().catch(() => undefined);
    }, 45000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!now?.next_best_action?.reminder_id || !now.next_best_action.scheduled_for) return;
    const reminderId = now.next_best_action.reminder_id;
    const scheduled = new Date(now.next_best_action.scheduled_for);
    if (scheduled > new Date()) return;
    if (notifiedIds.current.has(reminderId)) return;
    if ("Notification" in window) {
      if (Notification.permission === "default") {
        Notification.requestPermission().catch(() => undefined);
      }
      if (Notification.permission === "granted") {
        new Notification("Plangraph", {
          body: now.next_best_action.title,
        });
        notifiedIds.current.add(reminderId);
      }
    }
  }, [now]);

  useEffect(() => {
    if (!lazyTask) return;
    if (!useLlm) {
      setLazySuggestion([
        "Reschedule to tomorrow",
        "Shrink to a 30-minute focus block",
        "Skip and archive for now",
      ]);
      return;
    }
    fetchLazySuggestions(lazyTask.title, lazyTask.notes)
      .then((data) => setLazySuggestion(data.suggestions))
      .catch(() =>
        setLazySuggestion([
          "Reschedule to tomorrow",
          "Shrink to a 30-minute focus block",
          "Skip and archive for now",
        ])
      );
  }, [lazyTask, useLlm]);

  const groupedTasks = useMemo(() => {
    const nowDate = new Date();
    const today = nowDate.toISOString().slice(0, 10);
    const tomorrow = new Date(nowDate.getTime() + 24 * 60 * 60 * 1000)
      .toISOString()
      .slice(0, 10);
    const mapped = tasks.map((task) => ({
      ...task,
      dueDate: task.due_at?.slice(0, 10) ?? task.window_start?.slice(0, 10),
      dueTime: task.due_at?.slice(11, 16) ?? task.window_start?.slice(11, 16),
      isToday: (task.due_at?.slice(0, 10) ?? "") === today,
      isTomorrow: (task.due_at?.slice(0, 10) ?? "") === tomorrow,
    }));
    const searched = mapped.filter((task) =>
      task.title.toLowerCase().includes(taskSearch.toLowerCase())
    );
    return {
      today: searched.filter(
        (task) => task.status === "active" && task.isToday
      ),
      tomorrow: searched.filter(
        (task) => task.status === "active" && task.isTomorrow
      ),
      later: searched.filter(
        (task) => task.status === "active" && !task.isToday && !task.isTomorrow
      ),
      completed: searched.filter((task) => task.status === "completed"),
    };
  }, [tasks, taskSearch]);

  const recentCards = useMemo(() => {
    const normalized = (value: string) => value.trim().toLowerCase();
    const durationForTask = (task: Task) => {
      if (task.window_start && task.window_end) {
        const start = parseISO(task.window_start);
        const end = parseISO(task.window_end);
        return Math.round((end.getTime() - start.getTime()) / 60000);
      }
      return 0;
    };
    const seen = new Map<string, { task: Task; count: number }>();
    tasks.forEach((task) => {
      const key = `${normalized(task.title)}::${durationForTask(task)}`;
      const existing = seen.get(key);
      if (existing) {
        existing.count += 1;
      } else {
        seen.set(key, { task, count: 1 });
      }
    });
    return Array.from(seen.values());
  }, [tasks]);

  async function handleParse() {
    setIsParsing(true);
    try {
      const response = await parsePlan(parseText);
      setParsedItems(response.items);
    } finally {
      setIsParsing(false);
    }
  }

  const speechSupported =
    typeof window !== "undefined" &&
    ("SpeechRecognition" in window || "webkitSpeechRecognition" in window);

  function startDictation() {
    if (!speechSupported) return;
    const SpeechRecognition =
      (window as { SpeechRecognition?: unknown }).SpeechRecognition ||
      (window as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition;
    if (!SpeechRecognition) return;
    const recognition = new (SpeechRecognition as new () => SpeechRecognition)();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => setIsDictating(true);
    recognition.onend = () => setIsDictating(false);
    recognition.onerror = () => setIsDictating(false);
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      setQuickAddText((prev) => `${prev} ${transcript}`.trim());
    };
    recognition.start();
  }

  async function handleQuickAddParse() {
    if (!quickAddText.trim()) return;
    setIsParsing(true);
    try {
      const response = await parsePlan(quickAddText);
      setParsedItems(response.items);
      setParseText(quickAddText);
      setQuickAddText("");
      setQuickAddDraft(null);
      setQuickAddSource(null);
      setQuickAddOpen(false);
      setPage("Add");
    } finally {
      setIsParsing(false);
    }
  }

  async function handleLazyAction(action: "reschedule" | "shrink" | "skip") {
    if (!lazyTask) return;
    if (action === "skip") {
      await updateTask(lazyTask.id, { status: "archived" });
    }
    if (action === "reschedule") {
      if (lazyTask.due_at) {
        const next = parseISO(lazyTask.due_at);
        next.setDate(next.getDate() + 1);
        await updateTask(lazyTask.id, { due_at: next.toISOString() });
      } else if (lazyTask.window_start && lazyTask.window_end) {
        const start = parseISO(lazyTask.window_start);
        const end = parseISO(lazyTask.window_end);
        start.setDate(start.getDate() + 1);
        end.setDate(end.getDate() + 1);
        await updateTask(lazyTask.id, {
          window_start: start.toISOString(),
          window_end: end.toISOString(),
        });
      }
    }
    if (action === "shrink") {
      if (lazyTask.window_start) {
        const start = parseISO(lazyTask.window_start);
        const end = new Date(start.getTime() + 30 * 60000);
        await updateTask(lazyTask.id, {
          window_end: end.toISOString(),
        });
      } else if (lazyTask.due_at) {
        const due = parseISO(lazyTask.due_at);
        const start = new Date(due.getTime() - 30 * 60000);
        const end = new Date(due.getTime() + 30 * 60000);
        await updateTask(lazyTask.id, {
          window_start: start.toISOString(),
          window_end: end.toISOString(),
          due_at: null,
        });
      }
    }
    setLazyTask(null);
    refreshTasks();
    refreshNow();
  }

  async function handleAddHabit(task: Task) {
    await updateTask(task.id, { recurrence: "daily", recurrence_detail: "habit" });
    refreshTasks();
  }

  async function handleCancelTask(task: Task) {
    await updateTask(task.id, { status: "archived" });
    refreshTasks();
  }

  async function handleSaveTemplate(task: Task) {
    await createTemplate({
      title: task.title,
      default_duration_min: 30,
      default_type: task.task_type,
      default_priority: task.priority,
      pinned: false,
    });
    refreshTemplates();
  }

  function buildDraftWindow(durationMinutes = 30) {
    const nowDate = new Date();
    const start = new Date(nowDate.getTime() + 60 * 60000);
    const end = new Date(start.getTime() + durationMinutes * 60000);
    return { start, end };
  }

  function selectTemplateDraft(template: Template) {
    const { start, end } = buildDraftWindow(template.default_duration_min);
    setQuickAddDraft({
      title: template.title,
      date: start.toISOString().slice(0, 10),
      due_time: null,
      window_start: start.toISOString(),
      window_end: end.toISOString(),
      priority: template.default_priority,
      recurrence: "none",
      recurrence_detail: null,
      confidence: 0.6,
      notes: null,
      task_type: template.default_type,
    });
    setQuickAddSource({ type: "template", id: template.id });
  }

  function selectRecentDraft(task: Task) {
    const { start, end } = buildDraftWindow(30);
    setQuickAddDraft({
      title: task.title,
      date: start.toISOString().slice(0, 10),
      due_time: null,
      window_start: start.toISOString(),
      window_end: end.toISOString(),
      priority: task.priority,
      recurrence: task.recurrence ? (task.recurrence as ParseItem["recurrence"]) : "none",
      recurrence_detail: task.recurrence_detail,
      confidence: 0.6,
      notes: task.notes,
      task_type: task.task_type,
    });
    setQuickAddSource({ type: "recent", id: task.id });
  }

  async function handleQuickAddConfirm() {
    if (!quickAddDraft || quickAddSubmitting) return;
    const payload = {
      title: quickAddDraft.title,
      notes: quickAddDraft.notes ?? null,
      due_at: combineDateTime(quickAddDraft.date, quickAddDraft.due_time),
      window_start: quickAddDraft.window_start,
      window_end: quickAddDraft.window_end,
      priority: quickAddDraft.priority,
      recurrence: quickAddDraft.recurrence === "none" ? null : quickAddDraft.recurrence,
      recurrence_detail: quickAddDraft.recurrence_detail,
      task_type: quickAddDraft.task_type ?? "other",
    };
    try {
      setQuickAddSubmitting(true);
      await createTasks([payload]);
      setQuickAddDraft(null);
      setQuickAddSource(null);
      setQuickAddOpen(false);
      refreshTasks();
      refreshNow();
    } catch (error) {
      showToast("Could not add the task. Please try again.");
      console.error(error);
    } finally {
      setQuickAddSubmitting(false);
    }
  }

  function updateWindowDate(item: ParseItem, dateValue: string) {
    if (!item.window_start || !item.window_end) {
      return { ...item, date: dateValue };
    }
    const start = parseISO(item.window_start);
    const end = parseISO(item.window_end);
    const duration = end.getTime() - start.getTime();
    const newStart = new Date(`${dateValue}T${format(start, "HH:mm")}:00`);
    const newEnd = new Date(newStart.getTime() + duration);
    return {
      ...item,
      date: dateValue,
      window_start: newStart.toISOString(),
      window_end: newEnd.toISOString(),
    };
  }

  function updateWindowTimes(item: ParseItem, startTime: string, endTime: string) {
    if (!item.date) return item;
    const start = new Date(`${item.date}T${startTime}:00`);
    let end = new Date(`${item.date}T${endTime}:00`);
    if (end < start) {
      end = new Date(end.getTime() + 24 * 60 * 60 * 1000);
    }
    return {
      ...item,
      window_start: start.toISOString(),
      window_end: end.toISOString(),
    };
  }

  async function handleSave() {
    const payloads = parsedItems.map((item) => {
      const dueAt = combineDateTime(item.date, item.due_time);
      return {
        title: item.title,
        notes: item.notes ?? null,
        due_at: dueAt,
        window_start: item.window_start,
        window_end: item.window_end,
        priority: item.priority,
        recurrence: item.recurrence === "none" ? null : item.recurrence,
        recurrence_detail: item.recurrence_detail,
        task_type: item.task_type ?? "other",
      };
    });
    await createTasks(payloads);
    setParseText("");
    setParsedItems([]);
    refreshTasks();
    refreshNow();
  }

  const suggestionCount = parsedItems.reduce(
    (acc, item) => acc + (item.recurrence_suggestions?.length ?? 0),
    0
  );

  function applyRecurrenceSuggestions() {
    const updated = parsedItems.map((item) => {
      if (!item.recurrence_suggestions?.length) {
        return item;
      }
      const suggestion = item.recurrence_suggestions[0];
      return {
        ...item,
        recurrence: suggestion.recurrence,
        recurrence_detail: suggestion.recurrence_detail,
      };
    });
    setParsedItems(updated);
  }

  async function handleReminder(action: string) {
    if (!now?.next_best_action?.reminder_id) {
      showToast("No reminder available for this task yet.");
      return;
    }
    if (reminderSubmitting) return;
    const reminderId = now.next_best_action.reminder_id;
    const payload = { action };
    if (import.meta.env.DEV) {
      console.log("reminderAction request", { reminderId, payload });
    }
    try {
      setReminderSubmitting(true);
      const response = await reminderAction(reminderId, action);
      if (import.meta.env.DEV) {
        console.log("reminderAction response", response);
      }
      refreshNow();
      refreshTasks();
      refreshInsights();
    } catch (error) {
      showToast("Reminder action failed. Please try again.");
      console.error(error);
    } finally {
      setReminderSubmitting(false);
    }
  }

  async function handleStatusToggle(task: Task) {
    const status = task.status === "completed" ? "active" : "completed";
    await updateTask(task.id, { status });
    refreshTasks();
  }

  function openEditTask(task: Task) {
    const source = task.due_at ?? task.window_start ?? new Date().toISOString();
    const dateValue = format(parseISO(source), "yyyy-MM-dd");
    const startValue = task.due_at
      ? format(parseISO(task.due_at), "HH:mm")
      : task.window_start
        ? format(parseISO(task.window_start), "HH:mm")
        : "";
    const endValue = task.window_end ? format(parseISO(task.window_end), "HH:mm") : "";
    setEditingTask(task);
    setEditDraft({
      title: task.title,
      date: dateValue,
      startTime: startValue,
      endTime: endValue,
      priority: task.priority,
      recurrence: (task.recurrence as ParseItem["recurrence"]) ?? "none",
    });
  }

  async function handleEditSave() {
    if (!editingTask || !editDraft) return;
    if (!editDraft.date || !editDraft.startTime) {
      showToast("Please provide a date and start time.");
      return;
    }
    const start = new Date(`${editDraft.date}T${editDraft.startTime}:00`);
    let end: Date | null = null;
    if (editDraft.endTime) {
      end = new Date(`${editDraft.date}T${editDraft.endTime}:00`);
      if (end < start) {
        end = new Date(end.getTime() + 24 * 60 * 60 * 1000);
      }
    }
    const payload: Partial<Task> = {
      title: editDraft.title,
      priority: editDraft.priority,
      recurrence: editDraft.recurrence === "none" ? null : editDraft.recurrence,
    };
    if (end) {
      payload.window_start = start.toISOString();
      payload.window_end = end.toISOString();
      payload.due_at = null;
    } else {
      payload.due_at = start.toISOString();
      payload.window_start = null;
      payload.window_end = null;
    }
    try {
      await updateTask(editingTask.id, payload);
      refreshTasks();
      refreshNow();
      setEditingTask(null);
      setEditDraft(null);
    } catch (error) {
      showToast("Could not save changes. Please try again.");
      console.error(error);
    }
  }

  async function handleSettingsChange(key: keyof Settings, value: string | number) {
    await updateSettings({ [key]: value });
    refreshSettings();
  }

  const policyPresets = [
    {
      key: "calm",
      label: "Calm nudges",
      values: {
        policy_mode: "adaptive",
        daily_budget: 6,
        quiet_hours_start: "23:30",
        quiet_hours_end: "07:00",
        lead_time_minutes: 20,
      },
    },
    {
      key: "minimal",
      label: "Minimal",
      values: {
        policy_mode: "adaptive",
        daily_budget: 3,
        quiet_hours_start: "22:30",
        quiet_hours_end: "08:00",
        lead_time_minutes: 15,
      },
    },
    {
      key: "strict",
      label: "Strict",
      values: {
        policy_mode: "adaptive",
        daily_budget: 10,
        quiet_hours_start: "00:00",
        quiet_hours_end: "06:30",
        lead_time_minutes: 25,
      },
    },
  ] as const;

  function formatWhyNow(whyNow?: WhyNow | null) {
    if (!whyNow?.reasons?.length) return null;
    return whyNow.reasons.join(" · ");
  }

  return (
    <div className="min-h-screen">
      {toastMessage && (
        <div className="fixed right-6 top-6 z-50 rounded-xl bg-ink px-4 py-3 text-sm text-white shadow-lg">
          {toastMessage}
        </div>
      )}
      <header className="bg-white shadow-sm">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <p className="text-xs uppercase text-slate">Plangraph (Life OS)</p>
            <h1 className="text-xl font-semibold">Plan your day with calm nudges.</h1>
          </div>
          <nav className="flex gap-2">
            {pages.map((item) => (
              <button
                key={item}
                className={`rounded-full px-4 py-2 text-sm font-medium ${
                  page === item
                    ? "bg-ink text-white"
                    : "border border-slate/20 text-slate"
                }`}
                onClick={() => setPage(item)}
              >
                {item}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-8 px-6 py-8">
        {page === "Now" && (
          <section className="grid gap-6 lg:grid-cols-[2fr,1fr]">
            <div className="space-y-6">
              <button
                className="w-full rounded-2xl bg-ink px-4 py-3 text-sm font-semibold text-white"
                onClick={() => setQuickAddOpen(true)}
              >
                Quick add
              </button>
              <div className="rounded-3xl bg-white p-6 shadow">
                <h2 className="text-lg font-semibold">Next best action</h2>
                {now?.next_best_action ? (
                  <div className="mt-4 space-y-4">
                    <div className="rounded-2xl border border-slate/10 bg-mist p-4">
                      <p className="text-sm uppercase text-slate">Priority {now.next_best_action.priority}</p>
                      <h3 className="text-xl font-semibold">{now.next_best_action.title}</h3>
                      <p className="text-sm text-slate">
                        {now.next_best_action.scheduled_for
                          ? formatReminderTime(now.next_best_action.scheduled_for)
                          : "Flexible window"}
                      </p>
                      <p className="mt-2 text-sm text-slate">
                        {formatWhyNow(now.next_best_action.why_now)}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-3">
                      <button
                        className="rounded-full bg-ink px-4 py-2 text-sm text-white disabled:opacity-50"
                        onClick={() => handleReminder("done")}
                        disabled={!now.next_best_action.reminder_id || reminderSubmitting}
                      >
                        Done
                      </button>
                      <button
                        className="rounded-full border border-slate/20 px-4 py-2 text-sm disabled:opacity-50"
                        onClick={() => handleReminder("snooze_10")}
                        disabled={!now.next_best_action.reminder_id || reminderSubmitting}
                      >
                        Snooze 10
                      </button>
                      <button
                        className="rounded-full border border-slate/20 px-4 py-2 text-sm disabled:opacity-50"
                        onClick={() => handleReminder("snooze_30")}
                        disabled={!now.next_best_action.reminder_id || reminderSubmitting}
                      >
                        Snooze 30
                      </button>
                      <button
                        className="rounded-full border border-slate/20 px-4 py-2 text-sm disabled:opacity-50"
                        onClick={() => handleReminder("dismiss")}
                        disabled={!now.next_best_action.reminder_id || reminderSubmitting}
                      >
                        Dismiss
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="mt-4 text-sm text-slate">No upcoming reminders. Add a plan to get started.</p>
                )}
              </div>

              <div className="rounded-3xl bg-white p-6 shadow">
                <h3 className="text-lg font-semibold">Upcoming 6 hours</h3>
                <ul className="mt-4 space-y-3">
                  {now?.next_6_hours.length ? (
                    now.next_6_hours.map((item) => (
                      <li
                        key={item.task_id}
                        className="rounded-2xl border border-slate/10 bg-mist p-4"
                      >
                        <p className="text-sm text-slate">{item.title ?? "Task"}</p>
                        <p className="font-medium">
                          {item.scheduled_for ? formatReminderTime(item.scheduled_for) : "Flexible"}
                        </p>
                        {formatWhyNow(item.why_now) && (
                          <p className="mt-1 text-xs text-slate">{formatWhyNow(item.why_now)}</p>
                        )}
                      </li>
                    ))
                  ) : (
                    <li className="text-sm text-slate">Nothing scheduled.</li>
                  )}
                </ul>
              </div>
            </div>

            <div className="rounded-3xl bg-white p-6 shadow">
              <button
                className="flex w-full items-center justify-between text-left"
                onClick={() => setLaterOpen((open) => !open)}
              >
                <h3 className="text-lg font-semibold">Later today</h3>
                <span className="text-sm text-slate">{laterOpen ? "Hide" : "Show"}</span>
              </button>
              {laterOpen && (
                <div className="mt-4 space-y-3">
                  {now?.later_today.length ? (
                    now.later_today.map((item) => (
                      <div key={item.task_id} className="rounded-2xl border border-slate/10 p-4">
                        <p className="text-sm text-slate">{item.title ?? "Task"}</p>
                        <p className="font-medium">
                          {item.scheduled_for ? formatReminderTime(item.scheduled_for) : "Flexible"}
                        </p>
                        {formatWhyNow(item.why_now) && (
                          <p className="mt-1 text-xs text-slate">{formatWhyNow(item.why_now)}</p>
                        )}
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-slate">Nothing later today.</p>
                  )}
                </div>
              )}
            </div>
          </section>
        )}

        {page === "Add" && (
          <section className="grid gap-6 lg:grid-cols-[1.1fr,1fr]">
            <div className="rounded-3xl bg-white p-6 shadow">
              <h2 className="text-lg font-semibold">Type your plan</h2>
              <p className="text-sm text-slate">Use natural language. The parser will structure it.</p>
              <button
                className="mt-4 w-full rounded-2xl border border-slate/20 px-4 py-3 text-sm font-semibold"
                onClick={() => setQuickAddOpen(true)}
              >
                Quick add
              </button>
              <textarea
                className="mt-4 h-40 w-full rounded-2xl border border-slate/20 p-4 text-sm"
                placeholder="Tomorrow 9:00 dentist. Every day 20:00 journal."
                value={parseText}
                onChange={(event) => setParseText(event.target.value)}
              />
              <div className="mt-4 flex gap-3">
                <button
                  className="rounded-full bg-ink px-4 py-2 text-sm text-white"
                  onClick={handleParse}
                  disabled={!parseText || isParsing}
                >
                  {isParsing ? "Parsing..." : "Parse"}
                </button>
                <button
                  className="rounded-full border border-slate/20 px-4 py-2 text-sm"
                  onClick={handleSave}
                  disabled={!parsedItems.length}
                >
                  Save
                </button>
              </div>
            </div>

            <div className="rounded-3xl bg-white p-6 shadow">
              <h2 className="text-lg font-semibold">Preview & edit</h2>
              {suggestionCount > 0 && (
                <button
                  className="mt-3 rounded-full border border-slate/20 px-4 py-2 text-xs"
                  onClick={applyRecurrenceSuggestions}
                >
                  Apply recurrence suggestions ({suggestionCount})
                </button>
              )}
              <div className="mt-4 space-y-4">
                {parsedItems.length ? (
                  parsedItems.map((item, index) => (
                    <div key={index} className="rounded-2xl border border-slate/10 p-4">
                      <input
                        className="w-full rounded-lg border border-slate/20 p-2 text-sm"
                        value={item.title}
                        onChange={(event) => {
                          const updated = [...parsedItems];
                          updated[index] = { ...item, title: event.target.value };
                          setParsedItems(updated);
                        }}
                      />
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <input
                          className="rounded-lg border border-slate/20 p-2 text-sm"
                          type="date"
                          value={item.date ?? item.window_start?.slice(0, 10) ?? ""}
                          onChange={(event) => {
                            const updated = [...parsedItems];
                            updated[index] = updateWindowDate(item, event.target.value);
                            setParsedItems(updated);
                          }}
                        />
                        {item.window_start && item.window_end ? (
                          <div>
                            <div className="flex gap-2">
                              <input
                                className="w-full rounded-lg border border-slate/20 p-2 text-sm"
                                type="time"
                                value={format(parseISO(item.window_start), "HH:mm")}
                                onChange={(event) => {
                                  const updated = [...parsedItems];
                                  const endTime = item.window_end
                                    ? format(parseISO(item.window_end), "HH:mm")
                                    : "00:00";
                                  updated[index] = updateWindowTimes(
                                    item,
                                    event.target.value,
                                    endTime
                                  );
                                  setParsedItems(updated);
                                }}
                              />
                              <input
                                className="w-full rounded-lg border border-slate/20 p-2 text-sm"
                                type="time"
                                value={format(parseISO(item.window_end), "HH:mm")}
                                onChange={(event) => {
                                  const updated = [...parsedItems];
                                  const startTime = item.window_start
                                    ? format(parseISO(item.window_start), "HH:mm")
                                    : "00:00";
                                  updated[index] = updateWindowTimes(
                                    item,
                                    startTime,
                                    event.target.value
                                  );
                                  setParsedItems(updated);
                                }}
                              />
                            </div>
                            {item.window_start.slice(0, 10) !== item.window_end.slice(0, 10) && (
                              <p className="mt-1 text-xs text-slate">Ends next day</p>
                            )}
                          </div>
                        ) : (
                          <input
                            className="rounded-lg border border-slate/20 p-2 text-sm"
                            type="time"
                            value={item.due_time ?? ""}
                            onChange={(event) => {
                              const updated = [...parsedItems];
                              updated[index] = { ...item, due_time: event.target.value };
                              setParsedItems(updated);
                            }}
                          />
                        )}
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <input
                          className="rounded-lg border border-slate/20 p-2 text-sm"
                          placeholder="Notes"
                          value={item.notes ?? ""}
                          onChange={(event) => {
                            const updated = [...parsedItems];
                            updated[index] = { ...item, notes: event.target.value };
                            setParsedItems(updated);
                          }}
                        />
                      </div>
                      <div className="mt-3 flex gap-3">
                        <select
                          className="rounded-lg border border-slate/20 p-2 text-sm"
                          value={item.priority}
                          onChange={(event) => {
                            const updated = [...parsedItems];
                            updated[index] = {
                              ...item,
                              priority: event.target.value as ParseItem["priority"],
                            };
                            setParsedItems(updated);
                          }}
                        >
                          <option value="low">Low</option>
                          <option value="med">Medium</option>
                          <option value="high">High</option>
                        </select>
                        <select
                          className="rounded-lg border border-slate/20 p-2 text-sm"
                          value={item.recurrence}
                          onChange={(event) => {
                            const updated = [...parsedItems];
                            updated[index] = {
                              ...item,
                              recurrence: event.target.value as ParseItem["recurrence"],
                            };
                            setParsedItems(updated);
                          }}
                        >
                          <option value="none">No recurrence</option>
                          <option value="daily">Daily</option>
                          <option value="weekly">Weekly</option>
                          <option value="every_2_days">Every 2 days</option>
                          <option value="custom">Custom</option>
                        </select>
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-slate">Nothing parsed yet.</p>
                )}
              </div>
            </div>
          </section>
        )}

        {page === "Tasks" && (
          <section className="rounded-3xl bg-white p-6 shadow">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <h2 className="text-lg font-semibold">Tasks</h2>
              <button
                className="rounded-full border border-slate/20 px-4 py-2 text-sm"
                onClick={() => setQuickAddOpen(true)}
              >
                Quick add
              </button>
            </div>
            <input
              className="mt-4 w-full rounded-2xl border border-slate/20 p-3 text-sm"
              placeholder="Search tasks"
              value={taskSearch}
              onChange={(event) => setTaskSearch(event.target.value)}
            />
            {(
              [
                { key: "today", label: "Today", items: groupedTasks.today },
                { key: "tomorrow", label: "Tomorrow", items: groupedTasks.tomorrow },
                { key: "later", label: "Later", items: groupedTasks.later },
                { key: "completed", label: "Completed", items: groupedTasks.completed },
              ] as const
            ).map((group) => (
              <div key={group.key} className="mt-6">
                <button
                  className="flex w-full items-center justify-between rounded-2xl border border-slate/10 px-4 py-3"
                  onClick={() =>
                    setTasksOpen((prev) => ({ ...prev, [group.key]: !prev[group.key] }))
                  }
                >
                  <span className="text-sm font-semibold">{group.label}</span>
                  <span className="text-xs text-slate">
                    {tasksOpen[group.key as keyof typeof tasksOpen] ? "Hide" : "Show"}
                  </span>
                </button>
                {tasksOpen[group.key as keyof typeof tasksOpen] && (
                  <div className="mt-3 space-y-3">
                    {group.items.length ? (
                      group.items.map((task) => (
                        <div
                          key={task.id}
                          className="rounded-2xl border border-slate/10 p-4"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-4">
                            <div>
                              <p className="text-sm text-slate">{formatTaskTime(task)}</p>
                              <h3 className="text-base font-semibold">{task.title}</h3>
                              <p className="text-sm text-slate">Priority {task.priority}</p>
                            </div>
                            <button
                              className={`rounded-full px-4 py-2 text-sm ${
                                task.status === "completed"
                                  ? "bg-emerald-500 text-white"
                                  : "border border-slate/20"
                              }`}
                              onClick={() => handleStatusToggle(task)}
                            >
                              {task.status === "completed" ? "Completed" : "Mark done"}
                            </button>
                          </div>
                          <div className="mt-3 flex flex-wrap gap-2">
                            <button
                              className="rounded-full border border-slate/20 px-3 py-1 text-xs"
                              onClick={() => handleAddHabit(task)}
                            >
                              Add to habit
                            </button>
                            <button
                              className="rounded-full border border-slate/20 px-3 py-1 text-xs"
                              onClick={() => handleSaveTemplate(task)}
                            >
                              Save as template
                            </button>
                            <button
                              className="rounded-full border border-slate/20 px-3 py-1 text-xs"
                              onClick={() => openEditTask(task)}
                            >
                              Edit
                            </button>
                            <button
                              className="rounded-full border border-slate/20 px-3 py-1 text-xs"
                              onClick={() => handleCancelTask(task)}
                            >
                              Cancel
                            </button>
                            <button
                              className="rounded-full border border-slate/20 px-3 py-1 text-xs"
                              onClick={() => setLazyTask(task)}
                            >
                              Lazy
                            </button>
                          </div>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-slate">Nothing here yet.</p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </section>
        )}

        {page === "Policy" && settings && (
          <section className="rounded-3xl bg-white p-6 shadow">
            <h2 className="text-lg font-semibold">Policy settings</h2>
            <div className="mt-6 grid gap-4 md:grid-cols-3">
              {policyPresets.map((preset) => (
                <button
                  key={preset.key}
                  className="rounded-2xl border border-slate/20 p-4 text-left"
                  onClick={() => updateSettings(preset.values).then(refreshSettings)}
                >
                  <p className="text-sm font-semibold">{preset.label}</p>
                  <p className="text-xs text-slate">
                    Budget {preset.values.daily_budget} • Quiet{" "}
                    {preset.values.quiet_hours_start}–{preset.values.quiet_hours_end}
                  </p>
                </button>
              ))}
            </div>
            <details className="mt-6 rounded-2xl border border-slate/10 p-4">
              <summary className="cursor-pointer text-sm font-semibold text-slate">
                Advanced settings
              </summary>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="space-y-2 text-sm">
                  <span className="text-slate">Daily notification budget</span>
                  <input
                    className="w-full rounded-xl border border-slate/20 p-3"
                    type="number"
                    min={1}
                    value={settings.daily_budget}
                    onChange={(event) =>
                      handleSettingsChange("daily_budget", Number(event.target.value))
                    }
                  />
                </label>
                <label className="space-y-2 text-sm">
                  <span className="text-slate">Quiet hours start</span>
                  <input
                    className="w-full rounded-xl border border-slate/20 p-3"
                    type="time"
                    value={settings.quiet_hours_start ?? ""}
                    onChange={(event) =>
                      handleSettingsChange("quiet_hours_start", event.target.value)
                    }
                  />
                </label>
                <label className="space-y-2 text-sm">
                  <span className="text-slate">Quiet hours end</span>
                  <input
                    className="w-full rounded-xl border border-slate/20 p-3"
                    type="time"
                    value={settings.quiet_hours_end ?? ""}
                    onChange={(event) =>
                      handleSettingsChange("quiet_hours_end", event.target.value)
                    }
                  />
                </label>
                <label className="space-y-2 text-sm">
                  <span className="text-slate">Lead time (minutes)</span>
                  <input
                    className="w-full rounded-xl border border-slate/20 p-3"
                    type="number"
                    min={5}
                    value={settings.lead_time_minutes}
                    onChange={(event) =>
                      handleSettingsChange("lead_time_minutes", Number(event.target.value))
                    }
                  />
                </label>
              </div>
            </details>
          </section>
        )}

        {page === "Insights" && insights && (
          <section className="grid gap-6 lg:grid-cols-2">
            {summary && (
              <div className="rounded-3xl bg-white p-6 shadow lg:col-span-2">
                <h2 className="text-lg font-semibold">Weekly Summary</h2>
                <div className="mt-3 grid gap-3 md:grid-cols-4">
                  <div className="rounded-2xl border border-slate/10 p-4">
                    <p className="text-xs uppercase text-slate">Completion rate</p>
                    <p className="text-lg font-semibold">
                      {Math.round(summary.metrics.completion_rate * 100)}%
                    </p>
                  </div>
                  <div className="rounded-2xl border border-slate/10 p-4">
                    <p className="text-xs uppercase text-slate">Notifications/day</p>
                    <p className="text-lg font-semibold">
                      {summary.metrics.notifications_per_day}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-slate/10 p-4">
                    <p className="text-xs uppercase text-slate">Notifs per completion</p>
                    <p className="text-lg font-semibold">
                      {summary.metrics.notifications_per_completion}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-slate/10 p-4">
                    <p className="text-xs uppercase text-slate">Missed proxy</p>
                    <p className="text-lg font-semibold">{summary.metrics.missed_rate_proxy}</p>
                  </div>
                </div>
                <p className="mt-4 text-sm text-slate">{summary.narrative}</p>
                <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate">
                  {summary.recommendations.map((rec, index) => (
                    <li key={index}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="rounded-3xl bg-white p-6 shadow">
              <h2 className="text-lg font-semibold">Notifications per day</h2>
              <div className="mt-4 h-64">
                <ResponsiveContainer>
                  <BarChart data={insights.notifications_per_day}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="value" fill="#0f172a" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="rounded-3xl bg-white p-6 shadow">
              <h2 className="text-lg font-semibold">Completions per day</h2>
              <div className="mt-4 h-64">
                <ResponsiveContainer>
                  <LineChart data={insights.completions_per_day}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <Tooltip />
                    <Line type="monotone" dataKey="value" stroke="#16a34a" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="rounded-3xl bg-white p-6 shadow">
              <h2 className="text-lg font-semibold">Missed rate proxy</h2>
              <div className="mt-4 h-64">
                <ResponsiveContainer>
                  <AreaChart data={insights.missed_rate_proxy}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <Tooltip />
                    <Area dataKey="value" stroke="#f97316" fill="#fed7aa" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="rounded-3xl bg-white p-6 shadow">
              <h2 className="text-lg font-semibold">Notifications per completion</h2>
              <div className="mt-4 h-64">
                <ResponsiveContainer>
                  <LineChart data={insights.notifications_per_completion}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <Tooltip />
                    <Line type="monotone" dataKey="value" stroke="#2563eb" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </section>
        )}
      </main>

      {quickAddOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate/40 px-4">
          <div className="w-full max-w-lg rounded-3xl bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">Quick add</h3>
              <button
                className="rounded-full border border-slate/20 px-3 py-1 text-xs"
                onClick={() => {
                  setQuickAddOpen(false);
                  setQuickAddDraft(null);
                  setQuickAddSource(null);
                }}
              >
                Close
              </button>
            </div>
            <p className="mt-2 text-sm text-slate">
              Pick a template or recent task to add it today. You can also dictate or type a plan.
            </p>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {templates.length ? (
                templates.map((template) => {
                  const selected = quickAddSource?.type === "template" && quickAddSource.id === template.id;
                  return (
                    <button
                      key={template.id}
                      className={`rounded-2xl border p-3 text-left ${
                        selected ? "border-emerald-400 bg-emerald-50" : "border-slate/10"
                      }`}
                      onClick={() => selectTemplateDraft(template)}
                    >
                      <p className="text-sm font-semibold">{template.title}</p>
                      <p className="text-xs text-slate">
                        {template.default_duration_min} min • {template.default_priority}
                      </p>
                    </button>
                  );
                })
              ) : (
                <p className="text-sm text-slate">No templates yet. Save one from a task.</p>
              )}
            </div>
            <div className="mt-4">
              <p className="text-xs uppercase text-slate">Recent tasks</p>
              <div className="mt-2 grid gap-2 md:grid-cols-2">
                {recentCards.slice(0, 4).map(({ task, count }) => {
                  const selected = quickAddSource?.type === "recent" && quickAddSource.id === task.id;
                  return (
                    <button
                      key={task.id}
                      className={`rounded-2xl border p-3 text-left ${
                        selected ? "border-emerald-400 bg-emerald-50" : "border-slate/10"
                      }`}
                      onClick={() => selectRecentDraft(task)}
                    >
                      <p className="text-sm font-semibold">{task.title}</p>
                      <p className="text-xs text-slate">{formatTaskTime(task)}</p>
                      <p className="text-xs text-slate">Used {count}×</p>
                    </button>
                  );
                })}
              </div>
            </div>
            {quickAddDraft && (
              <div className="mt-4 rounded-2xl border border-slate/10 bg-mist p-4">
                <p className="text-xs uppercase text-slate">Selected draft</p>
                <input
                  className="mt-2 w-full rounded-lg border border-slate/20 p-2 text-sm"
                  value={quickAddDraft.title}
                  onChange={(event) =>
                    setQuickAddDraft((draft) => (draft ? { ...draft, title: event.target.value } : draft))
                  }
                />
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <input
                    className="rounded-lg border border-slate/20 p-2 text-sm"
                    type="date"
                    value={quickAddDraft.date ?? quickAddDraft.window_start?.slice(0, 10) ?? ""}
                    onChange={(event) =>
                      setQuickAddDraft((draft) => (draft ? updateWindowDate(draft, event.target.value) : draft))
                    }
                  />
                  {quickAddDraft.window_start && quickAddDraft.window_end ? (
                    <div className="flex gap-2">
                      <input
                        className="w-full rounded-lg border border-slate/20 p-2 text-sm"
                        type="time"
                        value={format(parseISO(quickAddDraft.window_start), "HH:mm")}
                        onChange={(event) => {
                          setQuickAddDraft((draft) => {
                            if (!draft || !draft.window_end) return draft;
                            const endTime = format(parseISO(draft.window_end), "HH:mm");
                            return updateWindowTimes(draft, event.target.value, endTime);
                          });
                        }}
                      />
                      <input
                        className="w-full rounded-lg border border-slate/20 p-2 text-sm"
                        type="time"
                        value={format(parseISO(quickAddDraft.window_end), "HH:mm")}
                        onChange={(event) => {
                          setQuickAddDraft((draft) => {
                            if (!draft || !draft.window_start) return draft;
                            const startTime = format(parseISO(draft.window_start), "HH:mm");
                            return updateWindowTimes(draft, startTime, event.target.value);
                          });
                        }}
                      />
                    </div>
                  ) : (
                    <input
                      className="rounded-lg border border-slate/20 p-2 text-sm"
                      type="time"
                      value={quickAddDraft.due_time ?? ""}
                      onChange={(event) =>
                        setQuickAddDraft((draft) =>
                          draft ? { ...draft, due_time: event.target.value } : draft
                        )
                      }
                    />
                  )}
                </div>
                <div className="mt-3 flex flex-wrap gap-3">
                  <select
                    className="rounded-lg border border-slate/20 p-2 text-sm"
                    value={quickAddDraft.priority}
                    onChange={(event) =>
                      setQuickAddDraft((draft) =>
                        draft
                          ? { ...draft, priority: event.target.value as ParseItem["priority"] }
                          : draft
                      )
                    }
                  >
                    <option value="low">Low</option>
                    <option value="med">Medium</option>
                    <option value="high">High</option>
                  </select>
                  <button
                    className="rounded-full bg-ink px-4 py-2 text-sm text-white disabled:opacity-50"
                    onClick={handleQuickAddConfirm}
                    disabled={quickAddSubmitting}
                  >
                    {quickAddSubmitting ? "Adding..." : "Add task"}
                  </button>
                </div>
              </div>
            )}
            <div className="mt-4">
              <p className="text-xs uppercase text-slate">Or dictate</p>
              <textarea
                className="mt-2 h-24 w-full rounded-2xl border border-slate/20 p-3 text-sm"
                placeholder="Say: Tomorrow 9:00 dentist, 18:00 meal prep."
                value={quickAddText}
                onChange={(event) => setQuickAddText(event.target.value)}
              />
              <div className="mt-3 flex flex-wrap gap-3">
                <button
                  className="rounded-full bg-ink px-4 py-2 text-sm text-white"
                  onClick={handleQuickAddParse}
                  disabled={!quickAddText || isParsing}
                >
                  {isParsing ? "Parsing..." : "Parse"}
                </button>
                <button
                  className="rounded-full border border-slate/20 px-4 py-2 text-sm"
                  onClick={startDictation}
                  disabled={!speechSupported || isDictating}
                >
                  {speechSupported
                    ? isDictating
                      ? "Listening..."
                      : "Start dictation"
                    : "Dictation unavailable"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {editingTask && editDraft && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate/40 px-4">
          <div className="w-full max-w-lg rounded-3xl bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">Edit task</h3>
              <button
                className="rounded-full border border-slate/20 px-3 py-1 text-xs"
                onClick={() => {
                  setEditingTask(null);
                  setEditDraft(null);
                }}
              >
                Close
              </button>
            </div>
            <div className="mt-4 space-y-3">
              <input
                className="w-full rounded-lg border border-slate/20 p-2 text-sm"
                value={editDraft.title}
                onChange={(event) =>
                  setEditDraft((draft) => (draft ? { ...draft, title: event.target.value } : draft))
                }
              />
              <div className="grid gap-3 md:grid-cols-2">
                <input
                  className="rounded-lg border border-slate/20 p-2 text-sm"
                  type="date"
                  value={editDraft.date}
                  onChange={(event) =>
                    setEditDraft((draft) => (draft ? { ...draft, date: event.target.value } : draft))
                  }
                />
                <div className="flex gap-2">
                  <input
                    className="w-full rounded-lg border border-slate/20 p-2 text-sm"
                    type="time"
                    value={editDraft.startTime}
                    onChange={(event) =>
                      setEditDraft((draft) =>
                        draft ? { ...draft, startTime: event.target.value } : draft
                      )
                    }
                  />
                  <input
                    className="w-full rounded-lg border border-slate/20 p-2 text-sm"
                    type="time"
                    value={editDraft.endTime}
                    onChange={(event) =>
                      setEditDraft((draft) =>
                        draft ? { ...draft, endTime: event.target.value } : draft
                      )
                    }
                  />
                </div>
              </div>
              <div className="flex flex-wrap gap-3">
                <select
                  className="rounded-lg border border-slate/20 p-2 text-sm"
                  value={editDraft.priority}
                  onChange={(event) =>
                    setEditDraft((draft) =>
                      draft
                        ? { ...draft, priority: event.target.value as ParseItem["priority"] }
                        : draft
                    )
                  }
                >
                  <option value="low">Low</option>
                  <option value="med">Medium</option>
                  <option value="high">High</option>
                </select>
                <select
                  className="rounded-lg border border-slate/20 p-2 text-sm"
                  value={editDraft.recurrence}
                  onChange={(event) =>
                    setEditDraft((draft) =>
                      draft
                        ? { ...draft, recurrence: event.target.value as ParseItem["recurrence"] }
                        : draft
                    )
                  }
                >
                  <option value="none">No recurrence</option>
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="every_2_days">Every 2 days</option>
                  <option value="custom">Custom</option>
                </select>
              </div>
              <p className="text-xs text-slate">
                Leave end time blank to set a due time instead of a window.
              </p>
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                className="rounded-full bg-ink px-4 py-2 text-sm text-white"
                onClick={handleEditSave}
              >
                Save changes
              </button>
              <button
                className="rounded-full border border-slate/20 px-4 py-2 text-sm"
                onClick={() => {
                  setEditingTask(null);
                  setEditDraft(null);
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {lazyTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate/40 px-4">
          <div className="w-full max-w-lg rounded-3xl bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">Decision support</h3>
              <button
                className="rounded-full border border-slate/20 px-3 py-1 text-xs"
                onClick={() => setLazyTask(null)}
              >
                Close
              </button>
            </div>
            <p className="mt-2 text-sm text-slate">{lazyTask.title}</p>
            <p className="text-xs text-slate">{formatTaskTime(lazyTask)}</p>
            <div className="mt-4 space-y-2">
              {lazySuggestion.map((suggestion, index) => (
                <div key={index} className="rounded-2xl border border-slate/10 p-3 text-sm">
                  {suggestion}
                </div>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                className="rounded-full bg-ink px-4 py-2 text-sm text-white"
                onClick={() => handleLazyAction("reschedule")}
              >
                Reschedule
              </button>
              <button
                className="rounded-full border border-slate/20 px-4 py-2 text-sm"
                onClick={() => handleLazyAction("shrink")}
              >
                Shrink
              </button>
              <button
                className="rounded-full border border-slate/20 px-4 py-2 text-sm"
                onClick={() => handleLazyAction("skip")}
              >
                Skip
              </button>
            </div>
            <p className="mt-3 text-xs text-slate">
              {useLlm
                ? "Suggestions are tuned with LLM-aware nudges."
                : "Suggestions are based on deterministic rules."}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
