"use client";

import { AgentStep } from "@/lib/types";
import { CheckCircle2, Loader2, Circle, XCircle, Bot, Activity } from "lucide-react";

function StatusIcon({ status }: { status: AgentStep["status"] }) {
  switch (status) {
    case "completed":
      return <CheckCircle2 size={16} className="text-go shrink-0" />;
    case "processing":
      return <Loader2 size={16} className="text-wait shrink-0 animate-spin" />;
    case "error":
      return <XCircle size={16} className="text-avoid shrink-0" />;
    default:
      return <Circle size={16} className="text-text-muted shrink-0" />;
  }
}

const statusLabel: Record<AgentStep["status"], string> = {
  completed: "Ready",
  processing: "Synthesizing",
  pending: "Queued",
  error: "Fault",
};

export default function AgentStatusPanel({
  agents,
  title = "ORCA Multi-Agent Pipeline",
}: {
  agents: AgentStep[];
  title?: string;
}) {
  const completedCount = agents.filter((a) => a.status === "completed").length;
  const isAllDone = completedCount === agents.length;

  return (
    <div className="rounded-2xl border border-border bg-surface p-5 backdrop-blur flex flex-col justify-between shadow-md">
      <div>
        <div className="flex items-center justify-between pb-3 border-b border-border mb-3">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-cyan/10 border border-cyan/30 flex items-center justify-center text-cyan">
              <Bot size={14} />
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-text-muted font-bold">
                {title}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 text-xs font-mono">
            <span className={isAllDone ? "text-go" : "text-wait"}>
              {completedCount}/{agents.length}
            </span>
            <span className="text-text-muted">active</span>
          </div>
        </div>

        <div className="space-y-3">
          {agents.map((agent, index) => (
            <div
              key={agent.name}
              className={`p-2.5 rounded-xl border transition-all ${
                agent.status === "processing"
                  ? "bg-surface-light border-wait/40 shadow-sm"
                  : agent.status === "completed"
                  ? "bg-surface-light/40 border-border/70"
                  : "bg-surface/40 border-border/40 opacity-70"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className="text-[10px] font-mono text-text-muted w-3.5">
                    0{index + 1}
                  </span>
                  <StatusIcon status={agent.status} />
                  <span className="text-xs font-semibold text-text-primary truncate">
                    {agent.name}
                  </span>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {agent.latencyMs && (
                    <span className="text-[10px] font-mono text-text-muted">
                      {agent.latencyMs}ms
                    </span>
                  )}
                  <span
                    className={`text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded ${
                      agent.status === "completed"
                        ? "bg-go/10 text-go border border-go/30"
                        : agent.status === "processing"
                        ? "bg-wait/10 text-wait border border-wait/30 animate-pulse"
                        : agent.status === "error"
                        ? "bg-avoid/10 text-avoid border border-avoid/30"
                        : "bg-surface text-text-muted border border-border"
                    }`}
                  >
                    {statusLabel[agent.status]}
                  </span>
                </div>
              </div>

              {agent.detail && (
                <p className="text-[11px] text-text-muted mt-1.5 pl-6 font-mono truncate">
                  ↳ {agent.detail}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 pt-3 border-t border-border flex items-center justify-between text-[11px] text-text-muted">
        <div className="flex items-center gap-1.5 text-cyan">
          <Activity size={12} className="animate-spin" />
          <span>Consensus Architecture</span>
        </div>
        <span className="font-mono">Sync: 100% Real-time</span>
      </div>
    </div>
  );
}