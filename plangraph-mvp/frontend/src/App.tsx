import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { Insights, NowResponse, ParsedItem, Settings, Task } from "./types";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const tabs = ["Now", "Add", "Tasks", "Policy", "Insights"] as const;

type Tab = (typeof tabs)[number];

const formatDateTime = (value?: string | null) => {
  if (!value) return "Flexible";
  return new Date(value).toLocaleString();
};

const formatDate = (value?: string | null) => {
  if (!value) return "";
  return new Date(value).toLocaleDateString();
};

const formatTime = (value?: string | null) => {
  if (!value) return "";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("Now");
  const [nowState, setNowState] = useState<NowResponse | null>(null);
  const [planText, setPlanText] = useState("");
  const [parseItems, setParseItems] = useState<ParsedItem[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("today");
  const [notificationId, setNotificationId] = useState<number | null>(null);

  const refreshNow = () => api.now().then(setNowState);

  useEffect(() => {
    refreshNow();
    api.tasks().then(setTasks);
    api.settings().then(setSettings);
    api.insights().then(setInsights);
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      refreshNow();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!nowState?.next_best_action) return;
    const reminder = nowState.next_best_action;
    const scheduled = new Date(reminder.scheduled_for);
    if (scheduled <= new Date() && reminder.id !== notificationId) {
      if (Notification.permission === "default") {
        Notification.requestPermission();
      }
      if (Notification.permission === "granted") {
        new Notification("Plangraph", {
          body: reminder.title,
        });
      }
      setNotificationId(reminder.id);
    }
  }, [nowState, notificationId]);

  const filteredTasks = useMemo(() => {
    const today = new Date();
    return tasks.filter((task) => {
      if (search && !task.title.toLowerCase().includes(search.toLowerCase())) {
        return false;
      }
      if (filter === "today" && task.due_at) {
        return new Date(task.due_at).toDateString() === today.toDateString();
      }
      if (filter === "next7" && task.due_at) {
        const due = new Date(task.due_at);
        const diff = (due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24);
        return diff >= 0 && diff <= 7;
      }
      if (filter === "today" && !task.due_at) {
        return false;
      }
      return true;
    });
  }, [tasks, search, filter]);

  const handleParse = async () => {
    const response = await api.parse(planText);
    setParseItems(response.items);
  };

  const handleSaveParsed = async () => {
    await Promise.all(
      parseItems.map((item) =>
        api.createTask({
          title: item.title,
          notes: item.notes,
          date: item.date,
          due_time: item.due_time,
          window_start: item.window_start,
          window_end: item.window_end,
          priority: item.priority,
          recurrence: item.recurrence,
          recurrence_detail: item.recurrence_detail,
        })
      )
    );
    setPlanText("");
    setParseItems([]);
    const updated = await api.tasks();
    setTasks(updated);
    setActiveTab("Tasks");
  };

  const handleTaskToggle = async (task: Task) => {
    const updated = await api.updateTask(task.id, {
      status: task.status === "completed" ? "active" : "completed",
    });
    setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
  };

  const handleReminderAction = async (id: number, action: "done" | "snooze_10" | "snooze_30" | "dismiss") => {
    await api.reminderAction(id, action);
    refreshNow();
    const updated = await api.tasks();
    setTasks(updated);
  };

  const handleSettingsSave = async () => {
    if (!settings) return;
    const updated = await api.updateSettings(settings);
    setSettings(updated);
  };

  return (
    <div className="min-h-screen">
      <header className="bg-white shadow-sm">
        <div className="mx-auto max-w-6xl px-6 py-6 flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Plangraph</p>
            <h1 className="text-2xl font-semibold">Life OS</h1>
          </div>
          <nav className="flex gap-2">
            {tabs.map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 rounded-full text-sm ${
                  activeTab === tab ? "bg-ink text-white" : "bg-slate-100 text-slate-600"
                }`}
              >
                {tab}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {activeTab === "Now" && (
          <section className="grid gap-6 lg:grid-cols-[2fr,1fr]">
            <div className="bg-white rounded-2xl p-6 shadow-sm">
              <h2 className="text-lg font-semibold">Next best action</h2>
              {nowState?.next_best_action ? (
                <div className="mt-4 space-y-4">
                  <div>
                    <p className="text-xl font-semibold">{nowState.next_best_action.title}</p>
                    <p className="text-sm text-slate-500">
                      {formatDateTime(nowState.next_best_action.scheduled_for)}
                    </p>
                    <p className="mt-2 text-sm italic text-slate-600">“{nowState.why_now}”</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => handleReminderAction(nowState.next_best_action!.id, "done")}
                      className="rounded-lg bg-emerald-500 px-4 py-2 text-white"
                    >
                      Done
                    </button>
                    <button
                      onClick={() => handleReminderAction(nowState.next_best_action!.id, "snooze_10")}
                      className="rounded-lg bg-slate-100 px-4 py-2 text-slate-700"
                    >
                      Snooze 10
                    </button>
                    <button
                      onClick={() => handleReminderAction(nowState.next_best_action!.id, "snooze_30")}
                      className="rounded-lg bg-slate-100 px-4 py-2 text-slate-700"
                    >
                      Snooze 30
                    </button>
                    <button
                      onClick={() => handleReminderAction(nowState.next_best_action!.id, "dismiss")}
                      className="rounded-lg bg-slate-100 px-4 py-2 text-slate-700"
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              ) : (
                <p className="mt-4 text-sm text-slate-500">No reminders scheduled yet.</p>
              )}
            </div>
            <div className="space-y-6">
              <div className="bg-white rounded-2xl p-6 shadow-sm">
                <h3 className="font-semibold">Next 6 hours</h3>
                <ul className="mt-4 space-y-3">
                  {nowState?.next_6_hours.map((item) => (
                    <li key={item.id} className="flex items-center justify-between text-sm">
                      <span>{item.title}</span>
                      <span className="text-slate-500">{formatTime(item.scheduled_for)}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="bg-white rounded-2xl p-6 shadow-sm">
                <details>
                  <summary className="cursor-pointer font-semibold">Later today</summary>
                  <ul className="mt-4 space-y-3">
                    {nowState?.later_today.map((item) => (
                      <li key={item.id} className="flex items-center justify-between text-sm">
                        <span>{item.title}</span>
                        <span className="text-slate-500">{formatTime(item.scheduled_for)}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              </div>
            </div>
          </section>
        )}

        {activeTab === "Add" && (
          <section className="grid gap-6 lg:grid-cols-[2fr,3fr]">
            <div className="bg-white rounded-2xl p-6 shadow-sm space-y-4">
              <h2 className="text-lg font-semibold">Type your plan</h2>
              <textarea
                rows={8}
                value={planText}
                onChange={(event) => setPlanText(event.target.value)}
                className="w-full"
                placeholder="Example: Pay rent tomorrow at 09:00, review budget Friday."
              />
              <button
                onClick={handleParse}
                className="rounded-lg bg-ocean px-4 py-2 text-white"
              >
                Parse
              </button>
            </div>
            <div className="bg-white rounded-2xl p-6 shadow-sm">
              <h3 className="font-semibold">Preview & edit</h3>
              {parseItems.length === 0 ? (
                <p className="mt-4 text-sm text-slate-500">Parsed items will appear here.</p>
              ) : (
                <div className="mt-4 space-y-4">
                  {parseItems.map((item, index) => (
                    <div key={index} className="rounded-xl border border-slate-100 p-4">
                      <div className="grid gap-3 md:grid-cols-2">
                        <label className="text-sm">
                          Title
                          <input
                            value={item.title}
                            onChange={(event) => {
                              const value = event.target.value;
                              setParseItems((prev) =>
                                prev.map((entry, idx) =>
                                  idx === index ? { ...entry, title: value } : entry
                                )
                              );
                            }}
                            className="mt-1 w-full"
                          />
                        </label>
                        <label className="text-sm">
                          Date
                          <input
                            type="date"
                            value={item.date ?? ""}
                            onChange={(event) => {
                              const value = event.target.value || null;
                              setParseItems((prev) =>
                                prev.map((entry, idx) =>
                                  idx === index ? { ...entry, date: value } : entry
                                )
                              );
                            }}
                            className="mt-1 w-full"
                          />
                        </label>
                        <label className="text-sm">
                          Due time
                          <input
                            type="time"
                            value={item.due_time ?? ""}
                            onChange={(event) => {
                              const value = event.target.value || null;
                              setParseItems((prev) =>
                                prev.map((entry, idx) =>
                                  idx === index ? { ...entry, due_time: value } : entry
                                )
                              );
                            }}
                            className="mt-1 w-full"
                          />
                        </label>
                        <label className="text-sm">
                          Priority
                          <select
                            value={item.priority}
                            onChange={(event) => {
                              const value = event.target.value as ParsedItem["priority"];
                              setParseItems((prev) =>
                                prev.map((entry, idx) =>
                                  idx === index ? { ...entry, priority: value } : entry
                                )
                              );
                            }}
                            className="mt-1 w-full"
                          >
                            <option value="low">Low</option>
                            <option value="med">Medium</option>
                            <option value="high">High</option>
                          </select>
                        </label>
                      </div>
                      <p className="mt-3 text-xs text-slate-400">
                        Confidence: {(item.confidence * 100).toFixed(0)}%
                      </p>
                    </div>
                  ))}
                  <button
                    onClick={handleSaveParsed}
                    className="rounded-lg bg-ink px-4 py-2 text-white"
                  >
                    Save tasks
                  </button>
                </div>
              )}
            </div>
          </section>
        )}

        {activeTab === "Tasks" && (
          <section className="space-y-6">
            <div className="flex flex-wrap items-center gap-3">
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search tasks"
                className="min-w-[200px]"
              />
              <div className="flex gap-2">
                {[
                  { key: "today", label: "Today" },
                  { key: "next7", label: "Next 7" },
                  { key: "all", label: "All" },
                ].map((option) => (
                  <button
                    key={option.key}
                    onClick={() => setFilter(option.key)}
                    className={`rounded-full px-4 py-2 ${
                      filter === option.key ? "bg-ink text-white" : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid gap-4">
              {filteredTasks.map((task) => (
                <div key={task.id} className="rounded-2xl bg-white p-5 shadow-sm">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-lg font-semibold">{task.title}</h3>
                      <p className="text-sm text-slate-500">
                        {task.due_at
                          ? `Due ${formatDateTime(task.due_at)}`
                          : `Window ${formatDateTime(task.window_start)}`}
                      </p>
                      {task.notes && <p className="mt-2 text-sm text-slate-600">{task.notes}</p>}
                    </div>
                    <button
                      onClick={() => handleTaskToggle(task)}
                      className={`rounded-full px-3 py-1 text-xs ${
                        task.status === "completed"
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {task.status === "completed" ? "Completed" : "Mark done"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {activeTab === "Policy" && settings && (
          <section className="max-w-3xl space-y-6">
            <div className="rounded-2xl bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold">Policy</h2>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="text-sm">
                  Mode
                  <select
                    value={settings.policy_mode}
                    onChange={(event) =>
                      setSettings((prev) =>
                        prev ? { ...prev, policy_mode: event.target.value as Settings["policy_mode"] } : prev
                      )
                    }
                    className="mt-1 w-full"
                  >
                    <option value="baseline">Baseline</option>
                    <option value="adaptive">Adaptive</option>
                  </select>
                </label>
                <label className="text-sm">
                  Daily budget
                  <input
                    type="number"
                    value={settings.daily_budget}
                    onChange={(event) =>
                      setSettings((prev) => (prev ? { ...prev, daily_budget: Number(event.target.value) } : prev))
                    }
                    className="mt-1 w-full"
                  />
                </label>
                <label className="text-sm">
                  Quiet hours start
                  <input
                    type="time"
                    value={settings.quiet_hours_start ?? ""}
                    onChange={(event) =>
                      setSettings((prev) =>
                        prev ? { ...prev, quiet_hours_start: event.target.value } : prev
                      )
                    }
                    className="mt-1 w-full"
                  />
                </label>
                <label className="text-sm">
                  Quiet hours end
                  <input
                    type="time"
                    value={settings.quiet_hours_end ?? ""}
                    onChange={(event) =>
                      setSettings((prev) => (prev ? { ...prev, quiet_hours_end: event.target.value } : prev))
                    }
                    className="mt-1 w-full"
                  />
                </label>
                <label className="text-sm">
                  Lead time (min)
                  <input
                    type="number"
                    value={settings.lead_time_min}
                    onChange={(event) =>
                      setSettings((prev) => (prev ? { ...prev, lead_time_min: Number(event.target.value) } : prev))
                    }
                    className="mt-1 w-full"
                  />
                </label>
              </div>
              <button
                onClick={handleSettingsSave}
                className="mt-4 rounded-lg bg-ink px-4 py-2 text-white"
              >
                Save settings
              </button>
            </div>
          </section>
        )}

        {activeTab === "Insights" && (
          <section className="grid gap-6">
            <div className="rounded-2xl bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold">Notifications vs completions</h2>
              {insights && (
                <div className="mt-4 h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={insights.notifications_per_day}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <Tooltip />
                      <Legend />
                      <Area
                        type="monotone"
                        dataKey="value"
                        name="Notifications"
                        fill="#0ea5e9"
                        stroke="#0284c7"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
            <div className="rounded-2xl bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold">Completions per day</h2>
              {insights && (
                <div className="mt-4 h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={insights.completions_per_day}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <Tooltip />
                      <Legend />
                      <Area
                        type="monotone"
                        dataKey="value"
                        name="Completions"
                        fill="#34d399"
                        stroke="#059669"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
            <div className="rounded-2xl bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold">Notifications per completion</h2>
              {insights && (
                <div className="mt-4 h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={insights.notifications_per_completion}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <Tooltip />
                      <Legend />
                      <Area
                        type="monotone"
                        dataKey="value"
                        name="Ratio"
                        fill="#fbbf24"
                        stroke="#f59e0b"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
            <div className="rounded-2xl bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold">Missed rate proxy</h2>
              {insights && (
                <div className="mt-4 h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={insights.missed_rate_proxy}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <Tooltip />
                      <Legend />
                      <Area
                        type="monotone"
                        dataKey="value"
                        name="Missed"
                        fill="#f87171"
                        stroke="#ef4444"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </section>
        )}
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-6 py-6 text-xs text-slate-500">
          Notifications use the browser Notifications API and only work while this app is open.
        </div>
      </footer>
    </div>
  );
}
