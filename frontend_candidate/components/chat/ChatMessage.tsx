import { ChatMessage as ChatMessageType } from "@/lib/types";
import DecisionCard from "@/components/shared/DecisionCard";
import AgentStatusPanel from "@/components/shared/AgentStatusPanel";
import { Waves, Database, ChevronDown } from "lucide-react";
import { useState } from "react";

export default function ChatMessage({ message }: { message: ChatMessageType }) {
  const [showEvidence, setShowEvidence] = useState(false);
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end mb-4 md:mb-6">
        <div className="max-w-[85%] md:max-w-[70%] bg-cyan/10 border border-cyan/30 rounded-2xl rounded-tr-sm px-4 py-3">
          <p className="text-sm md:text-base text-text-primary">{message.text}</p>
          <p className="text-[10px] text-text-muted mt-1 text-right">{message.timestamp}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start mb-4 md:mb-6">
      <div className="max-w-[95%] md:max-w-[80%] w-full">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-7 h-7 rounded-full bg-cyan/20 border border-cyan/40 flex items-center justify-center shrink-0">
            <Waves size={14} className="text-cyan" />
          </div>
          <span className="text-xs font-medium text-cyan">ORCA</span>
          <span className="text-[10px] text-text-muted">{message.timestamp}</span>
        </div>

        <div className="bg-surface border border-border rounded-2xl rounded-tl-sm p-3 md:p-4 space-y-4">
          <p className="text-sm md:text-base text-text-primary">{message.text}</p>

          {message.decision && (
            <DecisionCard
              decision={message.decision}
              onViewEvidence={
                message.sources ? () => setShowEvidence((s) => !s) : undefined
              }
            />
          )}

          {message.agents && <AgentStatusPanel agents={message.agents} />}

          {message.sources && showEvidence && (
            <div className="rounded-xl border border-border bg-surface-light p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Database size={14} className="text-cyan" />
                  <span className="text-xs uppercase tracking-wider text-text-muted font-medium">
                    Data Sources
                  </span>
                </div>
                <button onClick={() => setShowEvidence(false)}>
                  <ChevronDown size={16} className="text-text-muted" />
                </button>
              </div>
              <div className="space-y-2">
                {message.sources.map((s) => (
                  <div key={s.label} className="flex justify-between text-xs">
                    <span className="text-text-primary">{s.label}</span>
                    <span className="text-text-muted">{s.fetchedAgo}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}