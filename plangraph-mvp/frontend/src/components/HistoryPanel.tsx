import type { HistoryEntry, HistoryPlan } from "../types";

interface HistoryPanelProps {
  entries: HistoryEntry[];
  plans: HistoryPlan[];
}

export default function HistoryPanel({ entries, plans }: HistoryPanelProps) {
  return (
    <div className="card">
      <div className="card-header">
        <div>
          <h2>History</h2>
          <p className="muted">Recent entries and plans stored in SQLite.</p>
        </div>
      </div>

      <div className="history-grid">
        <div>
          <h3>Entries</h3>
          <div className="table table-history-entries">
            <div className="table-row table-header">
              <span>Text</span>
              <span>Today</span>
              <span>Items</span>
              <span>Created</span>
            </div>
            {entries.map((entry) => (
              <div className="table-row" key={entry.id}>
                <span>{entry.text}</span>
                <span>{entry.today ?? "—"}</span>
                <span>{entry.item_count}</span>
                <span>{new Date(entry.created_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <h3>Plans</h3>
          <div className="table table-history-plans">
            <div className="table-row table-header">
              <span>Day</span>
              <span>Window</span>
              <span>Planned</span>
              <span>Unscheduled</span>
            </div>
            {plans.map((plan) => (
              <div className="table-row" key={plan.id}>
                <span>{plan.day}</span>
                <span>
                  {plan.day_start}–{plan.day_end}
                </span>
                <span>{plan.planned_count}</span>
                <span>{plan.unscheduled_count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
