import { CheckCircle2, Circle, CircleDashed, LoaderCircle, TriangleAlert } from "lucide-react";
import type { ToolActivityStep } from "@/lib/schemas/assistant";

export function ActivityTrace({ steps, demonstration = false }: { steps: ToolActivityStep[]; demonstration?: boolean }) {
  if (!steps.length) return null;
  return <section aria-label={demonstration ? "Demonstration activity trace" : "Verified deterministic activity"} className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--surface-muted)]/55 p-3">
    <div className="mb-2 flex items-center justify-between gap-2"><h4 className="text-xs font-bold uppercase tracking-[0.08em]">Activity</h4>{demonstration && <span className="text-xs font-semibold text-[var(--caution)]">Demonstration data</span>}</div>
    <ol className="space-y-2">{steps.map((step, index) => { const Icon = step.status === "complete" ? CheckCircle2 : step.status === "running" ? LoaderCircle : step.status === "partial" || step.status === "unavailable" ? TriangleAlert : step.status === "waiting" ? CircleDashed : Circle; return <li key={step.id} className="relative flex gap-2 text-sm"><Icon aria-hidden="true" className={`mt-0.5 size-4 shrink-0 ${step.status === "complete" ? "text-[var(--success)]" : step.status === "running" ? "animate-spin text-[var(--information)]" : step.status === "waiting" ? "text-[var(--muted-foreground)]" : "text-[var(--caution)]"}`} /><span><strong>{step.label}</strong><span className="ml-1 text-xs text-[var(--muted-foreground)]">{step.status}</span>{step.detail && <span className="block text-xs text-[var(--muted-foreground)]">{step.detail}</span>}</span>{index < steps.length - 1 && <span aria-hidden="true" className="absolute left-[0.45rem] top-5 h-3 border-l border-[var(--border)]" />}</li>; })}</ol>
  </section>;
}
