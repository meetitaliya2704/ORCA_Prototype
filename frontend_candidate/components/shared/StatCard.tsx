import { LucideIcon } from "lucide-react";

export default function StatCard({
  icon: Icon,
  label,
  value,
  unit,
  accent = "cyan",
}: {
  icon: LucideIcon;
  label: string;
  value: string | number;
  unit?: string;
  accent?: "cyan" | "go" | "wait" | "avoid";
}) {
  const accentColor = {
    cyan: "text-cyan",
    go: "text-go",
    wait: "text-wait",
    avoid: "text-avoid",
  }[accent];

  return (
    <div className="rounded-xl border border-border bg-surface p-4 flex items-center gap-3">
      <div className={`w-10 h-10 rounded-lg bg-surface-light flex items-center justify-center shrink-0 ${accentColor}`}>
        <Icon size={20} />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-text-muted truncate">{label}</p>
        <p className="text-lg font-display font-semibold text-text-primary">
          {value}
          {unit && <span className="text-sm text-text-muted ml-1">{unit}</span>}
        </p>
      </div>
    </div>
  );
}