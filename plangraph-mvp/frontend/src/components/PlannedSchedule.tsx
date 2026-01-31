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
      <div className="card-header">
        <div>
          <h2>Planned Schedule</h2>
          <p className="muted">Timeline view with reasons for each slot.</p>
        </div>
        <span className="pill">{items.length} items</span>
      </div>
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
      <div className="timeline">
        {items.map((item, index) => (
          <div className="timeline-row" key={`${item.title}-${index}`}>
            <div className="timeline-time">
              <span>
                {item.planned_start && item.planned_end
                  ? `${item.planned_start}–${item.planned_end}`
                  : "—"}
              </span>
            </div>
            <div className="timeline-dot" />
            <div className="timeline-card">
              <div className="timeline-header">
                <h3>{item.title}</h3>
                <span className={`status status-${item.status}`}>{item.status}</span>
              </div>
              <p className="muted">Type: {item.type}</p>
              <div className="timeline-meta">
                <span>{item.reason ?? "No reason provided."}</span>
                {item.reason && (
                  <span className="tooltip" title={item.reason}>
                    Why
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
