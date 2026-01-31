import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import ParsedItems from "./components/ParsedItems";
import type { PlannedItem, Reminder, ScheduleItem } from "./types";
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

const toMinutes = (timeValue: string) => {
  const [hours, minutes] = timeValue.split(":").map(Number);
  return hours * 60 + minutes;
};

const addMinutes = (timeValue: string, minutesToAdd: number) => {
  const total = toMinutes(timeValue) + minutesToAdd;
  const hours = Math.floor((total + 1440) % 1440 / 60);
  const minutes = (total + 1440) % 60;
  return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}`;
};

const tabs = [
  { id: "now", label: "Now" },
  { id: "tasks", label: "Tasks" },
  { id: "add", label: "Add" },
] as const;

type ContextTarget =
  | { kind: "task"; item: ScheduleItem }
  | { kind: "planned"; item: PlannedItem }
  | { kind: "reminder"; reminder: Reminder };

export default function App() {
  const today = useMemo(() => formatDate(new Date()), []);
  const [text, setText] = useState(initialText);
  const [todayInput, setTodayInput] = useState(today);
  const [items, setItems] = useState<ScheduleItem[]>([]);
  const [plannedItems, setPlannedItems] = useState<PlannedItem[]>([]);
  const [conflicts, setConflicts] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]["id"]>("now");
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [notificationStatus, setNotificationStatus] = useState(
    typeof Notification !== "undefined" ? Notification.permission : "unsupported"
  );
  const notifiedIds = useRef<Set<number>>(new Set());

  const [taskFilterRange, setTaskFilterRange] = useState<"today" | "week" | "all">("today");
  const [taskFilterType, setTaskFilterType] = useState("all");
  const [taskFilterStatus, setTaskFilterStatus] = useState("pending");
  const [taskSearch, setTaskSearch] = useState("");
  const [tasks, setTasks] = useState<ScheduleItem[]>([]);

  const [quickAdd, setQuickAdd] = useState({
    title: "",
    date: today,
    time: "",
    type: "task",
    priority: 1,
  });
  const [pasteText, setPasteText] = useState("");
  const [pastePreview, setPastePreview] = useState<ScheduleItem[]>([]);

  const [contextMenu, setContextMenu] = useState<{
    target: ContextTarget;
    x: number;
    y: number;
  } | null>(null);
  const [modal, setModal] = useState<{
    mode: "edit" | "reschedule";
    item: ScheduleItem;
  } | null>(null);
  const [laterTodayOpen, setLaterTodayOpen] = useState(false);

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

  const planDay = async (overrideItems?: ScheduleItem[]) => {
    setLoading(true);
    setError(null);
    const includesTomorrow = text.toLowerCase().includes("tomorrow");
    const day = includesTomorrow ? addDays(todayInput, 1) : todayInput;

    try {
      const data = await api.plan(day, DAY_START, DAY_END, overrideItems ?? items);
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

  const handleEnableNotifications = () => {
    if (typeof Notification === "undefined") {
      setNotificationStatus("unsupported");
      return;
    }
    Notification.requestPermission().then((permission) => setNotificationStatus(permission));
  };

  const handleReminderAction = async (id: number, action: "dismiss" | "snooze" | "done", snoozeMin?: number) => {
    await api.ackReminder(id, action, snoozeMin);
    await refreshReminders();
  };

  const loadTasks = async () => {
    const range = taskFilterRange;
    let from: string | undefined;
    let to: string | undefined;
    if (range === "today") {
      from = today;
      to = today;
    } else if (range === "week") {
      from = today;
      to = addDays(today, 7);
    }
    const typeFilter = taskFilterType === "all" ? undefined : taskFilterType;
    const statusFilter = taskFilterStatus === "all" ? undefined : taskFilterStatus;
    const data = await api.tasks({
      from,
      to,
      type: typeFilter,
      status: statusFilter,
      q: taskSearch || undefined,
    });
    setTasks(data.items);
  };

  const handleQuickAdd = async () => {
    if (!quickAdd.title.trim()) {
      return;
    }
    await api.createTask({
      title: quickAdd.title,
      type: quickAdd.type as "task" | "event" | "reminder",
      date: quickAdd.date,
      start_time: quickAdd.time || null,
      duration_min: 0,
      priority: quickAdd.priority,
    });
    setQuickAdd({ title: "", date: today, time: "", type: "task", priority: 1 });
    await loadTasks();
  };

  const handlePasteParse = async () => {
    const data = await api.parse(pasteText, todayInput);
    setPastePreview(data.items);
  };

  const handlePasteSave = async () => {
    if (!pasteText.trim()) {
      return;
    }
    await api.createEntry(pasteText, todayInput);
    setPasteText("");
    setPastePreview([]);
    await loadTasks();
  };

  const handlePastePlan = async () => {
    if (pastePreview.length === 0) {
      return;
    }
    setItems(pastePreview);
    setText(pasteText);
    await planDay(pastePreview);
    setActiveTab("now");
  };

  const handleContextMenu = (event: React.MouseEvent, target: ContextTarget) => {
    event.preventDefault();
    setContextMenu({ target, x: event.clientX, y: event.clientY });
  };

  const handleMenuClose = () => setContextMenu(null);

  const handleMenuAction = async (action: string) => {
    if (!contextMenu) return;
    const { target } = contextMenu;
    if (target.kind === "reminder") {
      if (action === "done") await handleReminderAction(target.reminder.id, "done");
      if (action === "dismiss") await handleReminderAction(target.reminder.id, "dismiss");
      if (action === "snooze-10") await handleReminderAction(target.reminder.id, "snooze", 10);
      if (action === "snooze-30") await handleReminderAction(target.reminder.id, "snooze", 30);
      if (action === "snooze-60") await handleReminderAction(target.reminder.id, "snooze", 60);
    } else {
      const item = target.item;
      if (!item.id) {
        handleMenuClose();
        return;
      }
      if (action === "done") await api.completeTask(item.id);
      if (action === "delete") await api.deleteTask(item.id);
      if (action === "snooze-10" && item.start_time) {
        await api.updateTask(item.id, { start_time: addMinutes(item.start_time, 10) });
      }
      if (action === "snooze-30" && item.start_time) {
        await api.updateTask(item.id, { start_time: addMinutes(item.start_time, 30) });
      }
      if (action === "snooze-60" && item.start_time) {
        await api.updateTask(item.id, { start_time: addMinutes(item.start_time, 60) });
      }
      if (action === "edit") setModal({ mode: "edit", item });
      if (action === "reschedule") setModal({ mode: "reschedule", item });
      await loadTasks();
    }
    handleMenuClose();
  };

  useEffect(() => {
    refreshReminders().catch(() => undefined);
    const interval = window.setInterval(() => {
      refreshReminders().catch(() => undefined);
    }, 15000);
    return () => window.clearInterval(interval);
  }, [notificationStatus]);

  useEffect(() => {
    loadTasks().catch(() => undefined);
  }, [taskFilterRange, taskFilterType, taskFilterStatus, taskSearch, activeTab]);

  useEffect(() => {
    if (!contextMenu) return;
    const handleClick = () => setContextMenu(null);
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setContextMenu(null);
    };
    window.addEventListener("click", handleClick);
    window.addEventListener("keydown", handleKey);
    return () => {
      window.removeEventListener("click", handleClick);
      window.removeEventListener("keydown", handleKey);
    };
  }, [contextMenu]);

  const nowMinutes = toMinutes(
    `${new Date().getHours().toString().padStart(2, "0")}:${new Date().getMinutes().toString().padStart(2, "0")}`
  );
  const upcoming = plannedItems.filter(
    (item) =>
      item.planned_start &&
      toMinutes(item.planned_start) >= nowMinutes &&
      toMinutes(item.planned_start) < nowMinutes + 360
  );
  const laterToday = plannedItems.filter(
    (item) => item.planned_start && toMinutes(item.planned_start) >= nowMinutes + 360
  );

  const groupedTasks = tasks.reduce<Record<string, ScheduleItem[]>>((acc, task) => {
    const key = task.date || "No date";
    if (!acc[key]) acc[key] = [];
    acc[key].push(task);
    return acc;
  }, {});

  return (
    <div className="app">
      <header className="hero">
        <div>
          <h1>Plangraph MVP</h1>
          <p>Fast, local scheduling with reminders and smart task placement.</p>
        </div>
        <div className="hero-meta">
          <span className="pill">Now / Tasks / Add</span>
          <span className="pill">Local Ollama</span>
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

      {activeTab === "now" && (
        <section className="stack">
          <section className="card">
            <div className="card-header">
              <div>
                <h2>Due Now</h2>
                <p className="muted">Reminders ready for action.</p>
              </div>
              <button className="ghost" onClick={handleEnableNotifications}>
                Enable notifications ({notificationStatus})
              </button>
            </div>
            {reminders.length === 0 ? (
              <p className="muted">Nothing due yet.</p>
            ) : (
              <div className="reminder-grid">
                {reminders.map((reminder) => (
                  <div
                    className="reminder-card"
                    key={reminder.id}
                    onContextMenu={(event) => handleContextMenu(event, { kind: "reminder", reminder })}
                  >
                    <div className="reminder-header">
                      <div>
                        <h3>{reminder.title}</h3>
                        <p className="muted">Due {new Date(reminder.due_at).toLocaleString()}</p>
                      </div>
                      <span className="pill pill-secondary">{reminder.kind}</span>
                    </div>
                    <p>{reminder.body ?? "No details"}</p>
                    <p className="muted">{reminder.reason ?? "No reason provided."}</p>
                    <div className="actions">
                      <button onClick={() => handleReminderAction(reminder.id, "done")}>Done</button>
                      <button className="ghost" onClick={() => handleReminderAction(reminder.id, "snooze", 10)}>
                        Snooze 10m
                      </button>
                      <button className="ghost" onClick={() => handleReminderAction(reminder.id, "dismiss")}>
                        Dismiss
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="card">
            <div className="card-header">
              <div>
                <h2>Next 6 hours</h2>
                <p className="muted">What is coming up based on the latest plan.</p>
              </div>
              <span className="pill">{upcoming.length} items</span>
            </div>
            {upcoming.length === 0 ? (
              <p className="muted">No upcoming items yet. Plan your day to see them here.</p>
            ) : (
              <div className="timeline">
                {upcoming.map((item, index) => (
                  <div
                    className="timeline-row"
                    key={`${item.title}-${index}`}
                    onContextMenu={(event) => handleContextMenu(event, { kind: "planned", item })}
                  >
                    <div className="timeline-time">
                      {item.planned_start}–{item.planned_end}
                    </div>
                    <div className="timeline-dot" />
                    <div className="timeline-card">
                      <div className="timeline-header">
                        <h3>{item.title}</h3>
                        <span className="pill pill-secondary">{item.type}</span>
                      </div>
                      <p className="muted">{item.reason ?? "Scheduled item"}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="card">
            <div className="card-header">
              <div>
                <h2>Later Today</h2>
                <p className="muted">Collapsed by default.</p>
              </div>
              <button className="ghost" onClick={() => setLaterTodayOpen((prev) => !prev)}>
                {laterTodayOpen ? "Hide" : "Show"}
              </button>
            </div>
            {laterTodayOpen && (
              <div className="timeline">
                {laterToday.length === 0 ? (
                  <p className="muted">No later items.</p>
                ) : (
                  laterToday.map((item, index) => (
                    <div
                      className="timeline-row"
                      key={`${item.title}-later-${index}`}
                      onContextMenu={(event) => handleContextMenu(event, { kind: "planned", item })}
                    >
                      <div className="timeline-time">
                        {item.planned_start}–{item.planned_end}
                      </div>
                      <div className="timeline-dot" />
                      <div className="timeline-card">
                        <div className="timeline-header">
                          <h3>{item.title}</h3>
                          <span className="pill pill-secondary">{item.type}</span>
                        </div>
                        <p className="muted">{item.reason ?? "Scheduled item"}</p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </section>
        </section>
      )}

      {activeTab === "tasks" && (
        <section className="stack">
          <section className="card">
            <div className="card-header">
              <div>
                <h2>All Tasks</h2>
                <p className="muted">Manage everything across days and types.</p>
              </div>
            </div>
            <div className="form-grid">
              <label className="field">
                <span>Range</span>
                <select value={taskFilterRange} onChange={(event) => setTaskFilterRange(event.target.value as "today" | "week" | "all")}>
                  <option value="today">Today</option>
                  <option value="week">This week</option>
                  <option value="all">All</option>
                </select>
              </label>
              <label className="field">
                <span>Type</span>
                <select value={taskFilterType} onChange={(event) => setTaskFilterType(event.target.value)}>
                  <option value="all">All</option>
                  <option value="task">Task</option>
                  <option value="event">Event</option>
                  <option value="reminder">Reminder</option>
                </select>
              </label>
              <label className="field">
                <span>Status</span>
                <select value={taskFilterStatus} onChange={(event) => setTaskFilterStatus(event.target.value)}>
                  <option value="pending">Pending</option>
                  <option value="done">Done</option>
                  <option value="dismissed">Dismissed</option>
                  <option value="all">All</option>
                </select>
              </label>
              <label className="field">
                <span>Search</span>
                <input value={taskSearch} onChange={(event) => setTaskSearch(event.target.value)} placeholder="Search tasks" />
              </label>
            </div>

            {Object.keys(groupedTasks).length === 0 ? (
              <p className="muted">No tasks match the filters.</p>
            ) : (
              Object.entries(groupedTasks).map(([dateKey, grouped]) => (
                <div key={dateKey} className="group-block">
                  <h3>{dateKey}</h3>
                  <div className="table table-parsed">
                    <div className="table-row table-header">
                      <span>Title</span>
                      <span>Date</span>
                      <span>Time</span>
                      <span>Status</span>
                      <span>Priority</span>
                      <span>Type</span>
                      <span>Notes</span>
                      <span>ID</span>
                    </div>
                    {grouped.map((task) => (
                      <div
                        className="table-row"
                        key={task.id}
                        onContextMenu={(event) => handleContextMenu(event, { kind: "task", item: task })}
                      >
                        <span>{task.title}</span>
                        <span>{task.date ?? "—"}</span>
                        <span>{task.start_time ?? "—"}</span>
                        <span>{task.status ?? "pending"}</span>
                        <span>{task.priority}</span>
                        <span>{task.type}</span>
                        <span>{task.notes ?? "—"}</span>
                        <span>{task.id}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))
            )}
          </section>
        </section>
      )}

      {activeTab === "add" && (
        <section className="stack">
          <section className="card">
            <div className="card-header">
              <div>
                <h2>Quick Add</h2>
                <p className="muted">Create a single task fast.</p>
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
                <span>Title</span>
                <input value={quickAdd.title} onChange={(event) => setQuickAdd({ ...quickAdd, title: event.target.value })} />
              </label>
              <label className="field">
                <span>Date</span>
                <input type="date" value={quickAdd.date} onChange={(event) => setQuickAdd({ ...quickAdd, date: event.target.value })} />
              </label>
              <label className="field">
                <span>Time</span>
                <input type="time" value={quickAdd.time} onChange={(event) => setQuickAdd({ ...quickAdd, time: event.target.value })} />
              </label>
              <label className="field">
                <span>Type</span>
                <select value={quickAdd.type} onChange={(event) => setQuickAdd({ ...quickAdd, type: event.target.value })}>
                  <option value="task">Task</option>
                  <option value="event">Event</option>
                  <option value="reminder">Reminder</option>
                </select>
              </label>
              <label className="field">
                <span>Priority</span>
                <input
                  type="number"
                  value={quickAdd.priority}
                  onChange={(event) => setQuickAdd({ ...quickAdd, priority: Number(event.target.value) })}
                />
              </label>
            </div>
            <div className="actions">
              <button onClick={handleQuickAdd}>Add</button>
            </div>
          </section>

          <section className="card">
            <div className="card-header">
              <div>
                <h2>Paste Plan</h2>
                <p className="muted">Parse a paragraph into tasks, then save them.</p>
              </div>
            </div>
            <label className="field">
              <span>Plan text</span>
              <textarea value={pasteText} onChange={(event) => setPasteText(event.target.value)} rows={4} />
            </label>
            <div className="actions">
              <button className="ghost" onClick={handlePasteParse}>
                Parse
              </button>
              <button onClick={handlePasteSave} disabled={!pasteText.trim()}>
                Save to Tasks
              </button>
              <button onClick={handlePastePlan} disabled={pastePreview.length === 0}>
                Plan Day
              </button>
            </div>
            {pastePreview.length > 0 && <ParsedItems items={pastePreview} />}
          </section>
        </section>
      )}

      {contextMenu && (
        <div className="context-menu" style={{ top: contextMenu.y, left: contextMenu.x }}>
          {contextMenu.target.kind === "reminder" ? (
            <>
              <button onClick={() => handleMenuAction("done")}>Mark done</button>
              <button onClick={() => handleMenuAction("snooze-10")}>Snooze 10m</button>
              <button onClick={() => handleMenuAction("snooze-30")}>Snooze 30m</button>
              <button onClick={() => handleMenuAction("snooze-60")}>Snooze 1h</button>
              <button onClick={() => handleMenuAction("dismiss")}>Dismiss</button>
            </>
          ) : (
            <>
              <button onClick={() => handleMenuAction("done")}>Mark done</button>
              <button onClick={() => handleMenuAction("snooze-10")}>Snooze 10m</button>
              <button onClick={() => handleMenuAction("snooze-30")}>Snooze 30m</button>
              <button onClick={() => handleMenuAction("snooze-60")}>Snooze 1h</button>
              <button onClick={() => handleMenuAction("reschedule")}>Reschedule…</button>
              <button onClick={() => handleMenuAction("edit")}>Edit…</button>
              <button onClick={() => handleMenuAction("delete")}>Delete</button>
            </>
          )}
        </div>
      )}

      {modal && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="card-header">
              <h2>{modal.mode === "edit" ? "Edit Task" : "Reschedule"}</h2>
              <button className="ghost" onClick={() => setModal(null)}>
                Close
              </button>
            </div>
            <div className="form-grid">
              {modal.mode === "edit" && (
                <label className="field">
                  <span>Title</span>
                  <input
                    value={modal.item.title}
                    onChange={(event) => setModal({ ...modal, item: { ...modal.item, title: event.target.value } })}
                  />
                </label>
              )}
              <label className="field">
                <span>Date</span>
                <input
                  type="date"
                  value={modal.item.date ?? ""}
                  onChange={(event) => setModal({ ...modal, item: { ...modal.item, date: event.target.value } })}
                />
              </label>
              <label className="field">
                <span>Time</span>
                <input
                  type="time"
                  value={modal.item.start_time ?? ""}
                  onChange={(event) => setModal({ ...modal, item: { ...modal.item, start_time: event.target.value } })}
                />
              </label>
              {modal.mode === "edit" && (
                <label className="field">
                  <span>Type</span>
                  <select
                    value={modal.item.type}
                    onChange={(event) =>
                      setModal({ ...modal, item: { ...modal.item, type: event.target.value as ScheduleItem["type"] } })
                    }
                  >
                    <option value="task">Task</option>
                    <option value="event">Event</option>
                    <option value="reminder">Reminder</option>
                  </select>
                </label>
              )}
              {modal.mode === "edit" && (
                <label className="field">
                  <span>Priority</span>
                  <input
                    type="number"
                    value={modal.item.priority}
                    onChange={(event) =>
                      setModal({ ...modal, item: { ...modal.item, priority: Number(event.target.value) } })
                    }
                  />
                </label>
              )}
            </div>
            <div className="actions">
              <button
                onClick={async () => {
                  if (!modal.item.id) return;
                  await api.updateTask(modal.item.id, {
                    title: modal.item.title,
                    date: modal.item.date,
                    start_time: modal.item.start_time,
                    type: modal.item.type,
                    priority: modal.item.priority,
                  });
                  await loadTasks();
                  setModal(null);
                }}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {error && <p className="error">{error}</p>}
      {loading && <p className="muted">Working...</p>}
    </div>
  );
}
