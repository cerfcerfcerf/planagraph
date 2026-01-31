import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import ParsedItems from "./components/ParsedItems";
import PlannedSchedule from "./components/PlannedSchedule";
import RemindersPanel from "./components/RemindersPanel";
import HabitsPanel from "./components/HabitsPanel";
import HistoryPanel from "./components/HistoryPanel";
import type {
  HabitRule,
  HistoryEntry,
  HistoryPlan,
  PlannedItem,
  Reminder,
  ScheduleItem,
} from "./types";
import "./App.css";

const DAY_START = "07:00";
const DAY_END = "21:00";

const initialText =
  "Tomorrow school at 8. Take pills at 7:30. After school buy snacks. Don't forget headphones.";

const formatDate = (value: Date) => value.toISOString().slice(0, 10);

const addDays = (value: string, days: number) => {
  const [year, month, day] = value.split("-").map(Number);
  const base = new Date(year, month - 1, day);
  base.setDate(base.getDate() + days);
  return formatDate(base);
};

const tabs = [
  { id: "planner", label: "Planner" },
  { id: "reminders", label: "Reminders" },
  { id: "habits", label: "Habits" },
  { id: "history", label: "History" },
] as const;

export default function App() {
  const today = useMemo(() => formatDate(new Date()), []);
  const [text, setText] = useState(initialText);
  const [todayInput, setTodayInput] = useState(today);
  const [items, setItems] = useState<ScheduleItem[]>([]);
  const [plannedItems, setPlannedItems] = useState<PlannedItem[]>([]);
  const [conflicts, setConflicts] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]["id"]>("planner");
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [notificationStatus, setNotificationStatus] = useState(
    typeof Notification !== "undefined" ? Notification.permission : "unsupported"
  );
  const [habitRules, setHabitRules] = useState<HabitRule[]>([]);
  const [historyEntries, setHistoryEntries] = useState<HistoryEntry[]>([]);
  const [historyPlans, setHistoryPlans] = useState<HistoryPlan[]>([]);
  const notifiedIds = useRef<Set<number>>(new Set());

  const parseItems = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.parse(text, todayInput);
      setItems(data.items);
      setPlannedItems([]);
      setConflicts([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const saveEntry = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.createEntry(text, todayInput);
      setItems(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const planDay = async () => {
    setLoading(true);
    setError(null);
    const includesTomorrow = text.toLowerCase().includes("tomorrow");
    const day = includesTomorrow ? addDays(todayInput, 1) : todayInput;

    try {
      const data = await api.plan(day, DAY_START, DAY_END, items);
      setPlannedItems(data.planned);
      setConflicts(data.conflicts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const refreshReminders = async () => {
    try {
      const data = await api.remindersDue();
      setReminders(data.reminders);
      if (notificationStatus === "granted") {
        data.reminders.forEach((reminder) => {
          if (notifiedIds.current.has(reminder.id)) {
            return;
          }
          notifiedIds.current.add(reminder.id);
          new Notification(reminder.title, {
            body: reminder.body ?? "Reminder is due.",
          });
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  };

  const loadHabits = async () => {
    const data = await api.habitRules();
    setHabitRules(data.rules);
  };

  const loadHistory = async () => {
    const data = await api.history();
    setHistoryEntries(data.entries);
    setHistoryPlans(data.plans);
  };

  const handleReminderAction = async (id: number, action: "dismiss" | "snooze" | "done") => {
    await api.ackReminder(id, action, action === "snooze" ? 10 : undefined);
    await refreshReminders();
  };

  const handleEnableNotifications = () => {
    if (typeof Notification === "undefined") {
      setNotificationStatus("unsupported");
      return;
    }
    Notification.requestPermission().then((permission) => setNotificationStatus(permission));
  };

  const handleSaveHabit = async (rule: {
    key: string;
    title: string;
    lead_min: number;
    enabled: boolean;
    default_time?: string | null;
    target_per_week?: number | null;
  }) => {
    await api.upsertHabitRule(rule);
    await loadHabits();
  };

  useEffect(() => {
    loadHabits().catch(() => undefined);
    loadHistory().catch(() => undefined);
    refreshReminders().catch(() => undefined);
    const interval = window.setInterval(() => {
      refreshReminders().catch(() => undefined);
    }, 15000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    if (activeTab === "habits") {
      loadHabits().catch(() => undefined);
    }
    if (activeTab === "history") {
      loadHistory().catch(() => undefined);
    }
  }, [activeTab]);

  const dueBanner = reminders.length > 0 && (
    <div className="banner">
      <strong>{reminders.length} reminder(s) due now.</strong>
      <span>Open the Reminders tab to respond.</span>
    </div>
  );

  return (
    <div className="app">
      <header className="hero">
        <div>
          <h1>Plangraph MVP</h1>
          <p>Parse natural language into a structured daily plan with adaptive reminders.</p>
        </div>
        <div className="hero-meta">
          <span className="pill">Local Ollama</span>
          <span className="pill">SQLite persistence</span>
        </div>
      </header>

      {dueBanner}

      <nav className="tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === "planner" && (
        <section className="stack">
          <section className="card">
            <div className="card-header">
              <div>
                <h2>Input</h2>
                <p className="muted">Describe your day and let the planner schedule it.</p>
              </div>
            </div>
            <div className="form-grid">
              <label className="field">
                <span>Today</span>
                <input
                  type="date"
                  value={todayInput}
                  onChange={(event) => setTodayInput(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Notes</span>
                <textarea
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  rows={4}
                />
              </label>
            </div>
            <div className="actions">
              <button onClick={parseItems} disabled={loading}>
                Parse
              </button>
              <button className="ghost" onClick={saveEntry} disabled={loading}>
                Save Entry
              </button>
              <button onClick={planDay} disabled={loading || items.length === 0}>
                Plan Day
              </button>
            </div>
            {error && <p className="error">{error}</p>}
          </section>

          <ParsedItems items={items} />

          <PlannedSchedule items={plannedItems} conflicts={conflicts} />
        </section>
      )}

      {activeTab === "reminders" && (
        <RemindersPanel
          reminders={reminders}
          onDone={(id) => handleReminderAction(id, "done")}
          onSnooze={(id) => handleReminderAction(id, "snooze")}
          onDismiss={(id) => handleReminderAction(id, "dismiss")}
          onEnableNotifications={handleEnableNotifications}
          notificationStatus={notificationStatus}
        />
      )}

      {activeTab === "habits" && <HabitsPanel rules={habitRules} onSave={handleSaveHabit} />}

      {activeTab === "history" && <HistoryPanel entries={historyEntries} plans={historyPlans} />}
    </div>
  );
}
