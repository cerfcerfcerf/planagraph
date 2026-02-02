import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type { NowResponse, Reminder, ScheduleItem } from "./types";
import "./App.css";

const formatDate = (value: Date) => value.toISOString().slice(0, 10);

const addDays = (value: string, days: number) => {
  const [year, month, day] = value.split("-").map(Number);
  const base = new Date(year, month - 1, day);
  base.setDate(base.getDate() + days);
  return formatDate(base);
};

const formatTime = (isoString: string) =>
  new Date(isoString).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

const emptyPlanMessage = "Add an activity to start. Example: ‘School tomorrow 8:00, gym 17:30’.";

const tabs = [
  { id: "now", label: "Now" },
  { id: "add", label: "Add" },
  { id: "tasks", label: "Tasks" },
] as const;

type TaskMenuState = {
  item: ScheduleItem;
  anchor: { x: number; y: number };
};

export default function App() {
  const today = useMemo(() => formatDate(new Date()), []);
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]["id"]>("now");
  const [nowData, setNowData] = useState<NowResponse | null>(null);
  const [showAllDue, setShowAllDue] = useState(false);
  const [showLaterToday, setShowLaterToday] = useState(false);
  const [notificationStatus, setNotificationStatus] = useState(
    typeof Notification !== "undefined" ? Notification.permission : "unsupported"
  );
  const [notificationToast, setNotificationToast] = useState(false);
  const notifiedIds = useRef<Set<number>>(new Set());

  const [quickAddOpen, setQuickAddOpen] = useState(false);
  const [quickAdd, setQuickAdd] = useState({ text: "", date: today, time: "", priority: 1 });

  const [pasteText, setPasteText] = useState("");
  const [pastePreview, setPastePreview] = useState<ScheduleItem[]>([]);

  const [taskRange, setTaskRange] = useState<"today" | "week" | "all">("today");
  const [taskSearch, setTaskSearch] = useState("");
  const [tasks, setTasks] = useState<ScheduleItem[]>([]);
  const [taskMenu, setTaskMenu] = useState<TaskMenuState | null>(null);
  const [taskModal, setTaskModal] = useState<ScheduleItem | null>(null);

  const refreshNow = async () => {
    const data = await api.now();
    setNowData(data);
    if (notificationStatus === "granted") {
      data.due_now.forEach((reminder) => {
        if (notifiedIds.current.has(reminder.id)) {
          return;
        }
        notifiedIds.current.add(reminder.id);
        new Notification(reminder.title, {
          body: reminder.body ?? reminder.context ?? "Reminder is due.",
        });
      });
    }
  };

  const handleEnableNotifications = () => {
    if (typeof Notification === "undefined") {
      setNotificationStatus("unsupported");
      return;
    }
    Notification.requestPermission().then((permission) => setNotificationStatus(permission));
  };

  const handleReminderAction = async (
    id: number,
    action: "done" | "snooze" | "cancel_forever" | "move",
    options?: { snoozeMin?: number; moveTo?: string }
  ) => {
    await api.ackReminder(id, action, options);
    await refreshNow();
  };

  const loadTasks = async () => {
    let from: string | undefined;
    let to: string | undefined;
    if (taskRange === "today") {
      from = today;
      to = today;
    }
    if (taskRange === "week") {
      from = today;
      to = addDays(today, 7);
    }
    const data = await api.tasks({ from, to, q: taskSearch || undefined });
    setTasks(data.items);
  };

  useEffect(() => {
    refreshNow().catch(() => undefined);
    const interval = window.setInterval(() => {
      refreshNow().catch(() => undefined);
    }, 15000);
    return () => window.clearInterval(interval);
  }, [notificationStatus]);

  useEffect(() => {
    loadTasks().catch(() => undefined);
  }, [taskRange, taskSearch, activeTab]);

  useEffect(() => {
    if (notificationStatus === "granted") {
      setNotificationToast(true);
      const timeout = window.setTimeout(() => setNotificationToast(false), 2500);
      return () => window.clearTimeout(timeout);
    }
    return undefined;
  }, [notificationStatus]);

  useEffect(() => {
    if (!taskMenu) return;
    const handleClick = () => setTaskMenu(null);
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setTaskMenu(null);
    };
    window.addEventListener("click", handleClick);
    window.addEventListener("keydown", handleKey);
    return () => {
      window.removeEventListener("click", handleClick);
      window.removeEventListener("keydown", handleKey);
    };
  }, [taskMenu]);

  const dueNow = nowData?.due_now ?? [];
  const dueNowVisible = showAllDue ? dueNow : dueNow.slice(0, 3);
  const nextSix = nowData?.next_six_hours ?? [];
  const laterToday = nowData?.later_today ?? [];

  const renderReminderCard = (reminder: Reminder, showActions = false) => (
    <article className="reminder-card" key={reminder.id}>
      <div className="reminder-card-header">
        <div>
          <h3>{reminder.title}</h3>
          <p className="muted">{formatTime(reminder.due_at)}</p>
        </div>
        <span className="pill pill-secondary">{reminder.kind}</span>
      </div>
      <p className="context">{reminder.context ?? reminder.body ?? "Stay on track."}</p>
      <details className="details">
        <summary>Why?</summary>
        <p className="muted">{reminder.reason ?? "This reminder keeps your day on track."}</p>
      </details>
      {showActions && (
        <div className="actions">
          <button onClick={() => handleReminderAction(reminder.id, "done")}>Done</button>
          <button className="ghost" onClick={() => handleReminderAction(reminder.id, "snooze", { snoozeMin: 10 })}>
            Snooze
          </button>
          <button className="ghost" onClick={() => handleReminderAction(reminder.id, "move")}>
            Move
          </button>
          <button className="ghost" onClick={() => handleReminderAction(reminder.id, "cancel_forever")}>
            Cancel
          </button>
        </div>
      )}
    </article>
  );

  return (
    <div className="app">
      <header className="hero">
        <div>
          <h1>Plangraph</h1>
          <p>See what to do now, act fast, and keep moving.</p>
        </div>
        <div className="hero-meta">
          <button className="ghost" onClick={handleEnableNotifications}>
            Notifications: {notificationStatus}
          </button>
        </div>
      </header>

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

      {notificationToast && <div className="toast">Notifications enabled.</div>}

      {activeTab === "now" && (
        <section className="stack">
          {nowData?.overlap_message && (
            <div className="banner">
              <span>{nowData.overlap_message}</span>
              {nowData.overlap_move_id && (
                <button
                  className="ghost"
                  onClick={() =>
                    handleReminderAction(nowData.overlap_move_id as number, "move", {
                      moveTo: nowData.overlap_move_to ?? undefined,
                    })
                  }
                >
                  Move to next available slot
                </button>
              )}
            </div>
          )}

          <section className="card">
            <div className="card-header">
              <div>
                <h2>Due now</h2>
                <p className="muted">Handle these before you close the app.</p>
              </div>
              {dueNow.length > 3 && (
                <button className="ghost" onClick={() => setShowAllDue((prev) => !prev)}>
                  {showAllDue ? "Show fewer" : "Show all"}
                </button>
              )}
            </div>
            {dueNow.length === 0 ? (
              <p className="muted">{nowData?.has_plan ? "You’re clear for now." : emptyPlanMessage}</p>
            ) : (
              <div className="reminder-grid">{dueNowVisible.map((reminder) => renderReminderCard(reminder, true))}</div>
            )}
          </section>

          <section className="card">
            <div className="card-header">
              <div>
                <h2>Next 6 hours</h2>
                <p className="muted">Upcoming reminders so you can stay ahead.</p>
              </div>
              <span className="pill">{nextSix.length}</span>
            </div>
            {nextSix.length === 0 ? (
              <p className="muted">Nothing scheduled in the next 6 hours.</p>
            ) : (
              <div className="reminder-list">{nextSix.map((reminder) => renderReminderCard(reminder))}</div>
            )}
          </section>

          <section className="card">
            <div className="card-header">
              <div>
                <h2>Later today</h2>
                <p className="muted">Keep the rest of your day flexible.</p>
              </div>
              <button className="ghost" onClick={() => setShowLaterToday((prev) => !prev)}>
                {showLaterToday ? "Hide" : "Show"}
              </button>
            </div>
            {showLaterToday && (
              <div className="reminder-list">
                {laterToday.length === 0 ? (
                  <p className="muted">Nothing else planned for today.</p>
                ) : (
                  laterToday.map((reminder) => renderReminderCard(reminder))
                )}
              </div>
            )}
          </section>
        </section>
      )}

      {activeTab === "add" && (
        <section className="stack">
          <section className="card add-card">
            <div className="card-header">
              <div>
                <h2>Add</h2>
                <p className="muted">Capture the next thing in one line.</p>
              </div>
            </div>
            <button className="plus-button" onClick={() => setQuickAddOpen(true)}>
              +
            </button>
          </section>

          <section className="card">
            <div className="card-header">
              <div>
                <h2>Paste plan</h2>
                <p className="muted">Paste a paragraph and preview the reminders.</p>
              </div>
            </div>
            <label className="field">
              <span>Plan text</span>
              <textarea value={pasteText} onChange={(event) => setPasteText(event.target.value)} rows={5} />
            </label>
            <div className="actions">
              <button
                className="ghost"
                onClick={async () => {
                  const data = await api.parse(pasteText, today);
                  setPastePreview(data.items);
                }}
              >
                Parse
              </button>
              <button
                onClick={async () => {
                  if (!pasteText.trim()) return;
                  await api.createEntry(pasteText, today);
                  setPasteText("");
                  setPastePreview([]);
                  await refreshNow();
                }}
                disabled={!pasteText.trim()}
              >
                Save
              </button>
              <button
                onClick={async () => {
                  if (pastePreview.length === 0) return;
                  await api.plan(today, "07:00", "21:00", pastePreview);
                  setActiveTab("now");
                  await refreshNow();
                }}
                disabled={pastePreview.length === 0}
              >
                Plan Today
              </button>
            </div>
            {pastePreview.length > 0 && (
              <ul className="preview-list">
                {pastePreview.map((item, index) => (
                  <li key={`${item.title}-${index}`}>
                    <strong>{item.title}</strong>{" "}
                    <span className="muted">
                      {item.start_time ? item.start_time : item.date ? item.date : "No time"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </section>
      )}

      {activeTab === "tasks" && (
        <section className="stack">
          <section className="card">
            <div className="card-header">
              <div>
                <h2>Tasks</h2>
                <p className="muted">Everything that fuels reminders.</p>
              </div>
              <div className="filter-group">
                <button className={taskRange === "today" ? "active-pill" : "ghost"} onClick={() => setTaskRange("today")}>
                  Today
                </button>
                <button className={taskRange === "week" ? "active-pill" : "ghost"} onClick={() => setTaskRange("week")}>
                  Next 7 days
                </button>
                <button className={taskRange === "all" ? "active-pill" : "ghost"} onClick={() => setTaskRange("all")}>
                  All
                </button>
              </div>
            </div>
            <input
              className="search"
              placeholder="Search tasks"
              value={taskSearch}
              onChange={(event) => setTaskSearch(event.target.value)}
            />
            <div className="task-list">
              {tasks.length === 0 ? (
                <p className="muted">No tasks yet. Add something to get started.</p>
              ) : (
                tasks.map((task) => (
                  <div key={task.id} className="task-row">
                    <div>
                      <h3>{task.title}</h3>
                      <p className="muted">
                        Next reminder: {task.next_reminder_at ? formatTime(task.next_reminder_at) : "Not scheduled"}
                      </p>
                    </div>
                    <div className="task-meta">
                      <span className="pill">{task.task_state ?? "pending"}</span>
                      <button
                        className="icon-button"
                        onClick={(event) => {
                          const rect = (event.target as HTMLElement).getBoundingClientRect();
                          setTaskMenu({ item: task, anchor: { x: rect.right, y: rect.bottom } });
                        }}
                      >
                        …
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </section>
      )}

      {quickAddOpen && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="card-header">
              <h2>Quick add</h2>
              <button className="ghost" onClick={() => setQuickAddOpen(false)}>
                Close
              </button>
            </div>
            <label className="field">
              <span>What is it?</span>
              <input
                placeholder="e.g. School tomorrow 8:00"
                value={quickAdd.text}
                onChange={(event) => setQuickAdd({ ...quickAdd, text: event.target.value })}
              />
            </label>
            <div className="form-grid">
              <label className="field">
                <span>Date</span>
                <input
                  type="date"
                  value={quickAdd.date}
                  onChange={(event) => setQuickAdd({ ...quickAdd, date: event.target.value })}
                />
              </label>
              <label className="field">
                <span>Time</span>
                <input
                  type="time"
                  value={quickAdd.time}
                  onChange={(event) => setQuickAdd({ ...quickAdd, time: event.target.value })}
                />
              </label>
            </div>
            <div className="priority-toggle">
              <span className="muted">Priority</span>
              {[
                { label: "Low", value: 0 },
                { label: "Med", value: 1 },
                { label: "High", value: 2 },
              ].map((option) => (
                <button
                  key={option.label}
                  className={quickAdd.priority === option.value ? "active-pill" : "ghost"}
                  onClick={() => setQuickAdd({ ...quickAdd, priority: option.value })}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div className="actions">
              <button
                onClick={async () => {
                  if (!quickAdd.text.trim()) return;
                  await api.quickAddTask({
                    title: quickAdd.text,
                    date: quickAdd.date,
                    time: quickAdd.time || undefined,
                    priority: quickAdd.priority,
                  });
                  setQuickAdd({ text: "", date: today, time: "", priority: 1 });
                  setQuickAddOpen(false);
                  await refreshNow();
                }}
              >
                Add
              </button>
            </div>
          </div>
        </div>
      )}

      {taskMenu && (
        <div className="context-menu" style={{ top: taskMenu.anchor.y, left: taskMenu.anchor.x }}>
          <button
            onClick={() => {
              setTaskModal(taskMenu.item);
              setTaskMenu(null);
            }}
          >
            Edit
          </button>
          <button
            onClick={async () => {
              if (!taskMenu.item.id) return;
              await api.removeTask(taskMenu.item.id);
              setTaskMenu(null);
              await loadTasks();
            }}
          >
            Delete
          </button>
          <button
            onClick={async () => {
              if (!taskMenu.item.id) return;
              await api.disableTaskReminders(taskMenu.item.id);
              setTaskMenu(null);
              await refreshNow();
            }}
          >
            Disable reminders
          </button>
        </div>
      )}

      {taskModal && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="card-header">
              <h2>Edit task</h2>
              <button className="ghost" onClick={() => setTaskModal(null)}>
                Close
              </button>
            </div>
            <div className="form-grid">
              <label className="field">
                <span>Title</span>
                <input
                  value={taskModal.title}
                  onChange={(event) => setTaskModal({ ...taskModal, title: event.target.value })}
                />
              </label>
              <label className="field">
                <span>Date</span>
                <input
                  type="date"
                  value={taskModal.date ?? ""}
                  onChange={(event) => setTaskModal({ ...taskModal, date: event.target.value })}
                />
              </label>
              <label className="field">
                <span>Time</span>
                <input
                  type="time"
                  value={taskModal.start_time ?? ""}
                  onChange={(event) => setTaskModal({ ...taskModal, start_time: event.target.value })}
                />
              </label>
            </div>
            <div className="actions">
              <button
                onClick={async () => {
                  if (!taskModal.id) return;
                  await api.editTask(taskModal.id, {
                    title: taskModal.title,
                    date: taskModal.date,
                    start_time: taskModal.start_time,
                  });
                  setTaskModal(null);
                  await loadTasks();
                }}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
