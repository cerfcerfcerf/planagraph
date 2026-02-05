import { useEffect, useMemo, useState } from "react";
import {
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
import { api } from "./api";
import type { InsightsResponse, NowResponse, ParsedItem, Settings, Task } from "./types";

const tabs = ["Now", "Add", "Tasks", "Policy", "Insights"] as const;

const priorityStyles: Record<string, string> = {
  high: "bg-rose-500/20 text-rose-100",
  med: "bg-amber-500/20 text-amber-100",
  low: "bg-emerald-500/20 text-emerald-100",
};

function App() {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>("Now");
  const [nowState, setNowState] = useState<NowResponse | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [insights, setInsights] = useState<InsightsResponse | null>(null);
  const [planText, setPlanText] = useState("");
  const [parsedItems, setParsedItems] = useState<ParsedItem[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("today");
  const [notificationEnabled, setNotificationEnabled] = useState(false);

  const refreshNow = () => api.getNow().then(setNowState).catch(() => undefined);
  const refreshTasks = () => api.listTasks().then((data) => setTasks(data.items));

  useEffect(() => {
    refreshNow();
    refreshTasks();
    api.getSettings().then(setSettings).catch(() => undefined);
    api.getInsights().then(setInsights).catch(() => undefined);
  }, []);

  useEffect(() => {
    const interval = setInterval(refreshNow, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (nowState?.next_reminder_id && notificationEnabled && Notification.permission === "granted") {
      new Notification("Plangraph reminder", {
        body: nowState.next_best_action?.title || "You have a reminder.",
      });
    }
  }, [nowState, notificationEnabled]);

  const filteredTasks = useMemo(() => {
    const now = new Date();
    const weekAhead = new Date(now);
    weekAhead.setDate(now.getDate() + 7);
    return tasks.filter((task) => {
      if (search && !task.title.toLowerCase().includes(search.toLowerCase())) {
        return false;
      }
      const due = task.due_at ? new Date(task.due_at) : task.window_start ? new Date(task.window_start) : null;
      if (filter === "today") {
        return due && due.toDateString() === now.toDateString();
      }
      if (filter === "next7") {
        return due && due <= weekAhead;
      }
      return true;
    });
  }, [tasks, search, filter]);

  const handleParse = async () => {
    const data = await api.parsePlan(planText);
    setParsedItems(data.items);
  };

  const handleSaveParsed = async () => {
    for (const item of parsedItems) {
      const dueAt = item.date && item.due_time ? `${item.date}T${item.due_time}:00` : null;
      await api.createTask({
        title: item.title,
        notes: item.notes,
        priority: item.priority,
        recurrence: item.recurrence === "none" ? null : item.recurrence,
        due_at: dueAt,
        window_start: item.window_start,
        window_end: item.window_end,
        status: "active",
      });
    }
    setPlanText("");
    setParsedItems([]);
    refreshTasks();
    refreshNow();
  };

  const requestNotifications = async () => {
    const permission = await Notification.requestPermission();
    setNotificationEnabled(permission === "granted");
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <header className="mb-8 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-3xl font-semibold">Plangraph (Life OS)</h1>
            <p className="text-slate-300">Local-first plans, reminders, and adaptive nudges.</p>
          </div>
          <button
            onClick={requestNotifications}
            className="rounded-full bg-slate-800 px-4 py-2 text-sm text-slate-100 hover:bg-slate-700"
          >
            {notificationEnabled ? "Notifications enabled" : "Enable notifications"}
          </button>
        </header>

        <nav className="mb-8 flex flex-wrap gap-3">
          {tabs.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                activeTab === tab ? "bg-indigo-500 text-white" : "bg-slate-800 text-slate-200"
              }`}
            >
              {tab}
            </button>
          ))}
        </nav>

        {activeTab === "Now" && nowState && (
          <section className="grid gap-6 lg:grid-cols-[2fr,1fr]">
            <div className="rounded-2xl bg-slate-900/70 p-6 shadow">
              <h2 className="text-xl font-semibold">Next best action</h2>
              <p className="mt-1 text-slate-300">{nowState.why_now}</p>
              {nowState.next_best_action ? (
                <div className="mt-6 rounded-xl bg-slate-800/60 p-4">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-lg font-semibold">{nowState.next_best_action.title}</p>
                      <p className="text-sm text-slate-300">
                        Due {nowState.next_best_action.due_at || nowState.next_best_action.window_start || "flex"}
                      </p>
                    </div>
                    <span
                      className={`rounded-full px-3 py-1 text-xs ${
                        priorityStyles[nowState.next_best_action.priority] || "bg-slate-700"
                      }`}
                    >
                      {nowState.next_best_action.priority}
                    </span>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <ActionButton
                      label="Done"
                      onClick={() =>
                        nowState.next_reminder_id &&
                        api.reminderAction(nowState.next_reminder_id, "done").then(refreshNow)
                      }
                    />
                    <ActionButton
                      label="Snooze 10"
                      onClick={() =>
                        nowState.next_reminder_id &&
                        api.reminderAction(nowState.next_reminder_id, "snooze_10").then(refreshNow)
                      }
                    />
                    <ActionButton
                      label="Snooze 30"
                      onClick={() =>
                        nowState.next_reminder_id &&
                        api.reminderAction(nowState.next_reminder_id, "snooze_30").then(refreshNow)
                      }
                    />
                    <ActionButton
                      label="Dismiss"
                      onClick={() =>
                        nowState.next_reminder_id &&
                        api.reminderAction(nowState.next_reminder_id, "dismiss").then(refreshNow)
                      }
                    />
                  </div>
                </div>
              ) : (
                <p className="mt-4 text-sm text-slate-400">No immediate tasks. Add something new.</p>
              )}
            </div>

            <div className="space-y-4">
              <Panel title="Next 6 hours">
                {nowState.next_6_hours.length ? (
                  <ul className="space-y-2">
                    {nowState.next_6_hours.map((item) => (
                      <li key={item.task_id} className="rounded-lg bg-slate-800/60 p-3 text-sm">
                        <div className="flex items-center justify-between">
                          <span>{item.title}</span>
                          <span className="text-xs text-slate-300">
                            {item.due_at || item.window_start || "flex"}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-slate-400">No upcoming tasks.</p>
                )}
              </Panel>
              <Panel title="Later today">
                {nowState.later_today.length ? (
                  <ul className="space-y-2">
                    {nowState.later_today.map((item) => (
                      <li key={item.task_id} className="rounded-lg bg-slate-800/60 p-3 text-sm">
                        <div className="flex items-center justify-between">
                          <span>{item.title}</span>
                          <span className="text-xs text-slate-300">
                            {item.due_at || item.window_start || "flex"}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-slate-400">Nothing else scheduled.</p>
                )}
              </Panel>
            </div>
          </section>
        )}

        {activeTab === "Add" && (
          <section className="grid gap-6 lg:grid-cols-[1.2fr,1fr]">
            <div className="rounded-2xl bg-slate-900/70 p-6 shadow">
              <h2 className="text-xl font-semibold">Type your plan</h2>
              <textarea
                value={planText}
                onChange={(event) => setPlanText(event.target.value)}
                className="mt-4 h-40 w-full rounded-xl border border-slate-700 bg-white/90 p-4 text-sm text-slate-900"
                placeholder="Example: tomorrow 9am dentist; weekly review Friday 4pm"
              />
              <div className="mt-4 flex gap-3">
                <button
                  onClick={handleParse}
                  className="rounded-full bg-indigo-500 px-4 py-2 text-sm font-medium text-white"
                >
                  Parse
                </button>
                <button
                  onClick={() => {
                    setPlanText("");
                    setParsedItems([]);
                  }}
                  className="rounded-full bg-slate-800 px-4 py-2 text-sm text-slate-200"
                >
                  Clear
                </button>
              </div>
            </div>
            <div className="rounded-2xl bg-slate-900/70 p-6 shadow">
              <h2 className="text-xl font-semibold">Preview</h2>
              {parsedItems.length ? (
                <div className="mt-4 space-y-3">
                  {parsedItems.map((item, index) => (
                    <div key={`${item.title}-${index}`} className="rounded-xl bg-slate-800/60 p-4">
                      <input
                        value={item.title}
                        onChange={(event) => {
                          const next = [...parsedItems];
                          next[index] = { ...item, title: event.target.value };
                          setParsedItems(next);
                        }}
                        className="w-full rounded-lg border border-slate-600 bg-white px-3 py-2 text-sm"
                      />
                      <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-300">
                        <span>{item.date || "today"}</span>
                        <span>{item.due_time || "flex window"}</span>
                        <span className={`rounded-full px-2 py-0.5 ${priorityStyles[item.priority]}`}>
                          {item.priority}
                        </span>
                      </div>
                    </div>
                  ))}
                  <button
                    onClick={handleSaveParsed}
                    className="w-full rounded-full bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950"
                  >
                    Save tasks
                  </button>
                </div>
              ) : (
                <p className="mt-4 text-sm text-slate-400">Parse a plan to preview tasks.</p>
              )}
            </div>
          </section>
        )}

        {activeTab === "Tasks" && (
          <section className="rounded-2xl bg-slate-900/70 p-6 shadow">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="flex flex-1 gap-3">
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search tasks"
                  className="w-full rounded-full border border-slate-700 bg-white px-4 py-2 text-sm"
                />
                <select
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                  className="rounded-full border border-slate-700 bg-white px-4 py-2 text-sm"
                >
                  <option value="today">Today</option>
                  <option value="next7">Next 7</option>
                  <option value="all">All</option>
                </select>
              </div>
            </div>
            <div className="mt-6 space-y-3">
              {filteredTasks.map((task) => (
                <div key={task.id} className="flex items-center justify-between rounded-xl bg-slate-800/60 p-4">
                  <div>
                    <p className="text-sm font-semibold">{task.title}</p>
                    <p className="text-xs text-slate-300">
                      {task.due_at || task.window_start || "flex"} · {task.status}
                    </p>
                  </div>
                  <button
                    onClick={() =>
                      api.updateTask(task.id, { status: task.status === "completed" ? "active" : "completed" }).then(
                        refreshTasks
                      )
                    }
                    className="rounded-full bg-slate-700 px-3 py-1 text-xs text-slate-100"
                  >
                    {task.status === "completed" ? "Reopen" : "Complete"}
                  </button>
                </div>
              ))}
              {!filteredTasks.length && <p className="text-sm text-slate-400">No tasks match.</p>}
            </div>
          </section>
        )}

        {activeTab === "Policy" && settings && (
          <section className="rounded-2xl bg-slate-900/70 p-6 shadow">
            <h2 className="text-xl font-semibold">Policy settings</h2>
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <label className="flex flex-col gap-2 text-sm">
                Mode
                <select
                  value={settings.policy_mode}
                  onChange={(event) =>
                    setSettings({ ...settings, policy_mode: event.target.value as Settings["policy_mode"] })
                  }
                  className="rounded-lg border border-slate-700 bg-white px-3 py-2"
                >
                  <option value="baseline">Baseline</option>
                  <option value="adaptive">Adaptive</option>
                </select>
              </label>
              <label className="flex flex-col gap-2 text-sm">
                Daily notification budget
                <input
                  type="number"
                  value={settings.daily_budget}
                  onChange={(event) => setSettings({ ...settings, daily_budget: Number(event.target.value) })}
                  className="rounded-lg border border-slate-700 bg-white px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-2 text-sm">
                Quiet hours start
                <input
                  type="time"
                  value={settings.quiet_hours_start}
                  onChange={(event) => setSettings({ ...settings, quiet_hours_start: event.target.value })}
                  className="rounded-lg border border-slate-700 bg-white px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-2 text-sm">
                Quiet hours end
                <input
                  type="time"
                  value={settings.quiet_hours_end}
                  onChange={(event) => setSettings({ ...settings, quiet_hours_end: event.target.value })}
                  className="rounded-lg border border-slate-700 bg-white px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-2 text-sm">
                Lead time (minutes)
                <input
                  type="number"
                  value={settings.lead_time_min}
                  onChange={(event) => setSettings({ ...settings, lead_time_min: Number(event.target.value) })}
                  className="rounded-lg border border-slate-700 bg-white px-3 py-2"
                />
              </label>
            </div>
            <button
              onClick={() => settings && api.updateSettings(settings).then(setSettings)}
              className="mt-6 rounded-full bg-indigo-500 px-4 py-2 text-sm font-semibold text-white"
            >
              Save policy
            </button>
          </section>
        )}

        {activeTab === "Insights" && insights && (
          <section className="grid gap-6 lg:grid-cols-2">
            <Panel title="Notifications per day">
              <div className="h-60">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={insights.notifications_per_day}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis dataKey="date" stroke="#94a3b8" />
                    <YAxis stroke="#94a3b8" />
                    <Tooltip />
                    <Line type="monotone" dataKey="count" stroke="#6366f1" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title="Completions per day">
              <div className="h-60">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={insights.completions_per_day}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis dataKey="date" stroke="#94a3b8" />
                    <YAxis stroke="#94a3b8" />
                    <Tooltip />
                    <Bar dataKey="count" fill="#22c55e" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title="Performance">
              <div className="space-y-2 text-sm text-slate-300">
                <p>Missed rate proxy: {(insights.missed_rate_proxy * 100).toFixed(0)}%</p>
                <p>Notifications per completion: {insights.notifications_per_completion.toFixed(2)}</p>
                <p>Total notifications: {insights.totals.notifications ?? 0}</p>
                <p>Total completions: {insights.totals.completions ?? 0}</p>
              </div>
            </Panel>
          </section>
        )}
      </div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl bg-slate-900/70 p-6 shadow">
      <h3 className="text-lg font-semibold">{title}</h3>
      <div className="mt-4">{children}</div>
    </div>
  );
}

function ActionButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="rounded-full bg-slate-700 px-3 py-1 text-xs font-semibold text-slate-100 hover:bg-slate-600"
    >
      {label}
    </button>
  );
}

export default App;
