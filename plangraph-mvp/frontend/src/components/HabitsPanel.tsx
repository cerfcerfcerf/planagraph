import { useState } from "react";
import type { HabitRule } from "../types";

interface HabitsPanelProps {
  rules: HabitRule[];
  onSave: (rule: {
    key: string;
    title: string;
    lead_min: number;
    enabled: boolean;
    default_time?: string | null;
    target_per_week?: number | null;
  }) => void;
}

const presets = [
  { key: "pills", title: "Take pills", lead_min: 10, default_time: "07:30", target_per_week: 7 },
  { key: "gym", title: "Gym session", lead_min: 30, default_time: "18:00", target_per_week: 3 },
  { key: "food_log", title: "Food log", lead_min: 10, default_time: "20:00", target_per_week: 7 },
  { key: "shower", title: "Evening shower", lead_min: 10, default_time: "21:30", target_per_week: 7 },
];

export default function HabitsPanel({ rules, onSave }: HabitsPanelProps) {
  const [form, setForm] = useState({
    key: "",
    title: "",
    lead_min: 10,
    enabled: true,
    default_time: "",
    target_per_week: "",
  });

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    onSave({
      key: form.key,
      title: form.title,
      lead_min: Number(form.lead_min),
      enabled: form.enabled,
      default_time: form.default_time || null,
      target_per_week: form.target_per_week ? Number(form.target_per_week) : null,
    });
    setForm({ key: "", title: "", lead_min: 10, enabled: true, default_time: "", target_per_week: "" });
  };

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <h2>Habits</h2>
          <p className="muted">Configure repeatable habits and let the engine learn your timing.</p>
        </div>
      </div>

      <div className="preset-grid">
        {presets.map((preset) => (
          <button
            key={preset.key}
            className="ghost"
            onClick={() =>
              setForm({
                key: preset.key,
                title: preset.title,
                lead_min: preset.lead_min,
                enabled: true,
                default_time: preset.default_time,
                target_per_week: String(preset.target_per_week),
              })
            }
          >
            Use {preset.title}
          </button>
        ))}
      </div>

      <form className="form-grid" onSubmit={handleSubmit}>
        <label className="field">
          <span>Key</span>
          <input
            value={form.key}
            onChange={(event) => setForm({ ...form, key: event.target.value })}
            required
          />
        </label>
        <label className="field">
          <span>Title</span>
          <input
            value={form.title}
            onChange={(event) => setForm({ ...form, title: event.target.value })}
            required
          />
        </label>
        <label className="field">
          <span>Lead minutes</span>
          <input
            type="number"
            value={form.lead_min}
            onChange={(event) => setForm({ ...form, lead_min: Number(event.target.value) })}
            min={0}
          />
        </label>
        <label className="field">
          <span>Default time</span>
          <input
            type="time"
            value={form.default_time}
            onChange={(event) => setForm({ ...form, default_time: event.target.value })}
          />
        </label>
        <label className="field">
          <span>Target per week</span>
          <input
            type="number"
            value={form.target_per_week}
            onChange={(event) => setForm({ ...form, target_per_week: event.target.value })}
          />
        </label>
        <label className="field inline">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
          />
          <span>Enabled</span>
        </label>
        <button type="submit">Save habit rule</button>
      </form>

      <div className="table table-habits">
        <div className="table-row table-header">
          <span>Title</span>
          <span>Key</span>
          <span>Lead</span>
          <span>Default</span>
          <span>Target/week</span>
          <span>Learned time</span>
          <span>Status</span>
        </div>
        {rules.map((rule) => (
          <div className="table-row" key={rule.id}>
            <span>{rule.title}</span>
            <span>{rule.key}</span>
            <span>{rule.lead_min}m</span>
            <span>{rule.default_time ?? "—"}</span>
            <span>{rule.target_per_week ?? "—"}</span>
            <span>{rule.typical_time ?? "—"}</span>
            <span>{rule.enabled ? "Enabled" : "Disabled"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
