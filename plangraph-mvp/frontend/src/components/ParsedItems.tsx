import type { ScheduleItem } from "../types";

interface ParsedItemsProps {
  items: ScheduleItem[];
}

export default function ParsedItems({ items }: ParsedItemsProps) {
  if (items.length === 0) {
    return <p className="muted">No items parsed yet.</p>;
  }

  return (
    <div className="card">
      <h2>Parsed Items</h2>
      <div className="table">
        <div className="table-row table-header">
          <span>Title</span>
          <span>Type</span>
          <span>Date</span>
          <span>Start</span>
          <span>End</span>
          <span>Duration</span>
          <span>Priority</span>
        </div>
        {items.map((item, index) => (
          <div className="table-row" key={`${item.title}-${index}`}>
            <span>{item.title}</span>
            <span>{item.type}</span>
            <span>{item.date ?? "—"}</span>
            <span>{item.start_time ?? "—"}</span>
            <span>{item.end_time ?? "—"}</span>
            <span>{item.duration_min || 0} min</span>
            <span>{item.priority}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
