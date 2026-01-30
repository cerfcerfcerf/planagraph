import { useMemo, useState } from "react";
import ParsedItems from "./components/ParsedItems";
import PlannedSchedule from "./components/PlannedSchedule";
import type { PlannedItem, ScheduleItem } from "./types";
import "./App.css";

const API_URL = "http://localhost:8000";
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

export default function App() {
  const today = useMemo(() => formatDate(new Date()), []);
  const [text, setText] = useState(initialText);
  const [todayInput, setTodayInput] = useState(today);
  const [items, setItems] = useState<ScheduleItem[]>([]);
  const [plannedItems, setPlannedItems] = useState<PlannedItem[]>([]);
  const [conflicts, setConflicts] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parseItems = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/parse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, today: todayInput }),
      });
      if (!response.ok) {
        throw new Error(`Parse failed: ${response.status}`);
      }
      const data = (await response.json()) as { items: ScheduleItem[] };
      setItems(data.items);
      setPlannedItems([]);
      setConflicts([]);
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
      const response = await fetch(`${API_URL}/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          day,
          day_start: DAY_START,
          day_end: DAY_END,
          items,
        }),
      });
      if (!response.ok) {
        throw new Error(`Plan failed: ${response.status}`);
      }
      const data = (await response.json()) as {
        day: string;
        planned: PlannedItem[];
        conflicts: string[];
      };
      setPlannedItems(data.planned);
      setConflicts(data.conflicts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header>
        <h1>Plangraph MVP</h1>
        <p>Parse natural language into a structured daily plan.</p>
      </header>

      <section className="card">
        <h2>Input</h2>
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
        <div className="actions">
          <button onClick={parseItems} disabled={loading}>
            Parse
          </button>
          <button onClick={planDay} disabled={loading || items.length === 0}>
            Plan Day
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </section>

      <ParsedItems items={items} />

      <PlannedSchedule items={plannedItems} conflicts={conflicts} />
    </div>
  );
}
