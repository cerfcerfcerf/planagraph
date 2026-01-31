import type { Reminder } from "../types";

interface RemindersPanelProps {
  reminders: Reminder[];
  onDone: (id: number) => void;
  onSnooze: (id: number) => void;
  onDismiss: (id: number) => void;
  onEnableNotifications: () => void;
  notificationStatus: string;
}

export default function RemindersPanel({
  reminders,
  onDone,
  onSnooze,
  onDismiss,
  onEnableNotifications,
  notificationStatus,
}: RemindersPanelProps) {
  return (
    <div className="card">
      <div className="card-header">
        <div>
          <h2>Reminders</h2>
          <p className="muted">Live reminders from your schedule and habits.</p>
        </div>
        <button className="ghost" onClick={onEnableNotifications}>
          Enable notifications ({notificationStatus})
        </button>
      </div>
      {reminders.length === 0 ? (
        <p className="muted">No reminders due yet.</p>
      ) : (
        <div className="reminder-grid">
          {reminders.map((reminder) => (
            <div className="reminder-card" key={reminder.id}>
              <div className="reminder-header">
                <div>
                  <h3>{reminder.title}</h3>
                  <p className="muted">Due {new Date(reminder.due_at).toLocaleString()}</p>
                </div>
                <span className="pill pill-secondary">{reminder.kind}</span>
              </div>
              <p>{reminder.body ?? "No details"}</p>
              {reminder.related_item_title && (
                <p className="muted">Linked item: {reminder.related_item_title}</p>
              )}
              {reminder.reason && (
                <p className="muted">
                  {reminder.reason} <span className="tooltip" title={reminder.reason}>Why</span>
                </p>
              )}
              <div className="actions">
                <button onClick={() => onDone(reminder.id)}>Done</button>
                <button className="ghost" onClick={() => onSnooze(reminder.id)}>
                  Snooze 10m
                </button>
                <button className="ghost" onClick={() => onDismiss(reminder.id)}>
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
