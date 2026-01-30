import type { PlannedItem } from "../types";

interface PlannedScheduleProps {
  items: PlannedItem[];
  conflicts: string[];
}

export default function PlannedSchedule({ items, conflicts }: PlannedScheduleProps) {
  if (items.length === 0) {
    return <p className="muted">No plan generated yet.</p>;
  }

  return (
    <div className="card">
      <h2>Planned Schedule</h2>
      {conflicts.length > 0 && (
        <div className="conflicts">
          <strong>Conflicts</strong>
          <ul>
            {conflicts.map((conflict, index) => (
              <li key={`${conflict}-${index}`}>{conflict}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="table table-plan">
        <div className="table-row table-header">
          <span>Time</span>
          <span>Title</span>
          <span>Status</span>
          <span>Reason</span>
        </div>
        {items.map((item, index) => (
          <div className="table-row" key={`${item.title}-${index}`}>
            <span>
              {item.planned_start && item.planned_end
                ? `${item.planned_start}–${item.planned_end}`
                : "—"}
            </span>
            <span>{item.title}</span>
            <span className={`status status-${item.status}`}>{item.status}</span>
            <span>{item.reason ?? "—"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
