import { useEffect, useMemo, useRef, useState } from "react";
import {
  createTasks,
  fetchInsights,
  fetchNow,
  fetchSettings,
  listTasks,
  parsePlan,
  reminderAction,
  updateSettings,
  updateTask,
} from "./api";
import type { InsightsResponse, NowResponse, ParseItem, Settings, Task } from "./types";
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

const pages = ["Now", "Add", "Tasks", "Policy", "Insights"] as const;

type Page = (typeof pages)[number];

function combineDateTime(dateValue: string | null, timeValue: string | null) {
  if (!dateValue || !timeValue) return null;
  return new Date(`${dateValue}T${timeValue}:00`).toISOString();
}

export default function App() {
  const [page, setPage] = useState<Page>("Now");
  const [parseText, setParseText] = useState("");
  const [parsedItems, setParsedItems] = useState<ParseItem[]>([]);
  const [isParsing, setIsParsing] = useState(false);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskFilter, setTaskFilter] = useState<"today" | "next7" | "all">("today");
  const [taskSearch, setTaskSearch] = useState("");
  const [laterOpen, setLaterOpen] = useState(true);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [now, setNow] = useState<NowResponse | null>(null);
  const [insights, setInsights] = useState<InsightsResponse | null>(null);
  const notifiedIds = useRef(new Set<number>());

  const refreshTasks = () => listTasks().then((data) => setTasks(data.tasks));

  const refreshSettings = () => fetchSettings().then(setSettings);

  const refreshNow = () => fetchNow().then(setNow);

  const refreshInsights = () => fetchInsights().then(setInsights);

  useEffect(() => {
    refreshTasks();
    refreshSettings();
    refreshNow();
    refreshInsights();
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

  const filteredTasks = useMemo(() => {
    const nowDate = new Date();
    const today = nowDate.toISOString().slice(0, 10);
    const nextWeek = new Date(nowDate.getTime() + 7 * 24 * 60 * 60 * 1000)
      .toISOString()
      .slice(0, 10);
    const mapped = tasks.map((task) => ({
      ...task,
      dueDate: task.due_at?.slice(0, 10) ?? task.window_start?.slice(0, 10),
      dueTime: task.due_at?.slice(11, 16) ?? task.window_start?.slice(11, 16),
      isToday: (task.due_at?.slice(0, 10) ?? "") === today,
      isNext7:
        (task.due_at?.slice(0, 10) ?? task.window_start?.slice(0, 10) ?? "") <=
        nextWeek,
    }));
    const searched = mapped.filter((task) =>
      task.title.toLowerCase().includes(taskSearch.toLowerCase())
    );
    if (taskFilter === "today") {
      return searched.filter((task) => task.isToday);
    }
    if (taskFilter === "next7") {
      return searched.filter((task) => task.isNext7);
    }
    return searched;
  }, [tasks, taskFilter, taskSearch]);

  async function handleParse() {
    setIsParsing(true);
    try {
      const response = await parsePlan(parseText);
      setParsedItems(response.items);
    } finally {
      setIsParsing(false);
    }
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
      };
    });
    await createTasks(payloads);
    setParseText("");
    setParsedItems([]);
    refreshTasks();
    refreshNow();
  }

  async function handleReminder(action: string) {
    if (!now?.next_best_action?.reminder_id) return;
    await reminderAction(now.next_best_action.reminder_id, action);
    refreshNow();
    refreshTasks();
  }

  async function handleStatusToggle(task: Task) {
    const status = task.status === "completed" ? "active" : "completed";
    await updateTask(task.id, { status });
    refreshTasks();
  }

  async function handleSettingsChange(key: keyof Settings, value: string | number) {
    await updateSettings({ [key]: value });
    refreshSettings();
  }

  return (
    <div className="min-h-screen">
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
              <div className="rounded-3xl bg-white p-6 shadow">
                <h2 className="text-lg font-semibold">Next best action</h2>
                {now?.next_best_action ? (
                  <div className="mt-4 space-y-4">
                    <div className="rounded-2xl border border-slate/10 bg-mist p-4">
                      <p className="text-sm uppercase text-slate">Priority {now.next_best_action.priority}</p>
                      <h3 className="text-xl font-semibold">{now.next_best_action.title}</h3>
                      <p className="text-sm text-slate">
                        Scheduled {now.next_best_action.scheduled_for ?? "flexible"}
                      </p>
                      <p className="mt-2 text-sm text-slate">{now.next_best_action.why_now}</p>
                    </div>
                    <div className="flex flex-wrap gap-3">
                      <button
                        className="rounded-full bg-ink px-4 py-2 text-sm text-white"
                        onClick={() => handleReminder("done")}
                      >
                        Done
                      </button>
                      <button
                        className="rounded-full border border-slate/20 px-4 py-2 text-sm"
                        onClick={() => handleReminder("snooze_10")}
                      >
                        Snooze 10
                      </button>
                      <button
                        className="rounded-full border border-slate/20 px-4 py-2 text-sm"
                        onClick={() => handleReminder("snooze_30")}
                      >
                        Snooze 30
                      </button>
                      <button
                        className="rounded-full border border-slate/20 px-4 py-2 text-sm"
                        onClick={() => handleReminder("dismiss")}
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
                        key={item.id}
                        className="rounded-2xl border border-slate/10 bg-mist p-4"
                      >
                        <p className="text-sm text-slate">Reminder #{item.id}</p>
                        <p className="font-medium">Scheduled {item.scheduled_for}</p>
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
                      <div key={item.id} className="rounded-2xl border border-slate/10 p-4">
                        <p className="text-sm text-slate">Reminder #{item.id}</p>
                        <p className="font-medium">Scheduled {item.scheduled_for}</p>
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
                          value={item.date ?? ""}
                          onChange={(event) => {
                            const updated = [...parsedItems];
                            updated[index] = { ...item, date: event.target.value };
                            setParsedItems(updated);
                          }}
                        />
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
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <input
                          className="rounded-lg border border-slate/20 p-2 text-sm"
                          placeholder="Window start"
                          value={item.window_start ?? ""}
                          onChange={(event) => {
                            const updated = [...parsedItems];
                            updated[index] = { ...item, window_start: event.target.value };
                            setParsedItems(updated);
                          }}
                        />
                        <input
                          className="rounded-lg border border-slate/20 p-2 text-sm"
                          placeholder="Window end"
                          value={item.window_end ?? ""}
                          onChange={(event) => {
                            const updated = [...parsedItems];
                            updated[index] = { ...item, window_end: event.target.value };
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
              <div className="flex flex-wrap gap-2">
                {(
                  [
                    { label: "Today", value: "today" },
                    { label: "Next 7", value: "next7" },
                    { label: "All", value: "all" },
                  ] as const
                ).map((filter) => (
                  <button
                    key={filter.value}
                    className={`rounded-full px-4 py-2 text-sm ${
                      taskFilter === filter.value
                        ? "bg-ink text-white"
                        : "border border-slate/20"
                    }`}
                    onClick={() => setTaskFilter(filter.value)}
                  >
                    {filter.label}
                  </button>
                ))}
              </div>
            </div>
            <input
              className="mt-4 w-full rounded-2xl border border-slate/20 p-3 text-sm"
              placeholder="Search tasks"
              value={taskSearch}
              onChange={(event) => setTaskSearch(event.target.value)}
            />
            <div className="mt-4 space-y-3">
              {filteredTasks.length ? (
                filteredTasks.map((task) => (
                  <div
                    key={task.id}
                    className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate/10 p-4"
                  >
                    <div>
                      <p className="text-sm text-slate">{task.dueDate ?? "Flexible"}</p>
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
                ))
              ) : (
                <p className="text-sm text-slate">No tasks yet.</p>
              )}
            </div>
          </section>
        )}

        {page === "Policy" && settings && (
          <section className="rounded-3xl bg-white p-6 shadow">
            <h2 className="text-lg font-semibold">Policy settings</h2>
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <label className="space-y-2 text-sm">
                <span className="text-slate">Mode</span>
                <select
                  className="w-full rounded-xl border border-slate/20 p-3"
                  value={settings.policy_mode}
                  onChange={(event) => handleSettingsChange("policy_mode", event.target.value)}
                >
                  <option value="baseline">Baseline</option>
                  <option value="adaptive">Adaptive</option>
                </select>
              </label>
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
                  onChange={(event) => handleSettingsChange("quiet_hours_start", event.target.value)}
                />
              </label>
              <label className="space-y-2 text-sm">
                <span className="text-slate">Quiet hours end</span>
                <input
                  className="w-full rounded-xl border border-slate/20 p-3"
                  type="time"
                  value={settings.quiet_hours_end ?? ""}
                  onChange={(event) => handleSettingsChange("quiet_hours_end", event.target.value)}
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
          </section>
        )}

        {page === "Insights" && insights && (
          <section className="grid gap-6 lg:grid-cols-2">
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
    </div>
  );
}
