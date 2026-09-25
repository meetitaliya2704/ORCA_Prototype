"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  MessageSquareText,
  Map as MapIcon,
  Bell,
  MessageSquare,
  Plus,
  Trash2,
  History,
} from "lucide-react";
import { useChatSessions } from "@/lib/chat-session-context";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/chat", label: "AI Chat", icon: MessageSquareText },
  { href: "/map", label: "Map", icon: MapIcon },
  { href: "/alerts", label: "Alerts", icon: Bell },
];

function formatRelativeTime(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { sessions, activeSessionId, startNewChat, switchSession, deleteSession } = useChatSessions();

  const handleNewChat = () => {
    startNewChat();
    router.push("/chat");
  };

  const handleSelectSession = (sessionId: string) => {
    switchSession(sessionId);
    router.push("/chat");
  };

  return (
    <>
      {/* Desktop / tablet sidebar */}
      <aside className="hidden md:flex md:flex-col w-60 lg:w-64 bg-surface border-r border-border shrink-0 h-full overflow-hidden">
        {/* Top Header */}
        <div className="flex items-center justify-between px-3.5 h-14 border-b border-border text-[11px] font-semibold uppercase tracking-wider text-text-muted shrink-0">
          <span className="font-mono text-text-primary font-bold">Console Deck</span>
          <span className="text-[10px] text-cyan bg-cyan/10 border border-cyan/30 px-1.5 py-0.5 rounded font-mono font-semibold">
            Live
          </span>
        </div>

        {/* Primary Navigation Items: AI Chat, Map, Alerts */}
        <nav className="py-3 flex flex-col gap-1 px-2 shrink-0">
          {navItems.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all ${
                  active
                    ? "bg-cyan/15 text-cyan border border-cyan/40 font-bold shadow-sm"
                    : "text-text-muted hover:bg-surface-light hover:text-text-primary border border-transparent"
                }`}
              >
                <Icon size={18} className="shrink-0" />
                <span className="text-xs font-semibold">{label}</span>
              </Link>
            );
          })}
        </nav>

        {/* ChatGPT-style Chat History Section below Alerts */}
        <div className="flex-1 min-h-0 flex flex-col px-2 pt-3 pb-3 border-t border-border overflow-hidden">
          {/* Header with Title & + New Chat Button */}
          <div className="flex items-center justify-between px-1.5 mb-2 shrink-0">
            <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-muted flex items-center gap-1.5">
              <History size={12} className="text-cyan" />
              <span>Chat History</span>
              {sessions.length > 0 && (
                <span className="text-[10px] font-mono text-cyan bg-cyan/10 px-1.5 py-0.2 rounded-full font-bold">
                  {sessions.length}
                </span>
              )}
            </span>
            <button
              type="button"
              onClick={handleNewChat}
              className="px-2 py-0.5 rounded-md text-[11px] font-semibold bg-surface-light hover:bg-surface border border-border text-cyan hover:text-cyan/80 flex items-center gap-1 transition-all shadow-sm"
              title="Start a new chat conversation"
            >
              <Plus size={12} />
              <span>New</span>
            </button>
          </div>

          {/* Scrollable list of past conversations */}
          <div className="flex-1 overflow-y-auto space-y-1 pr-1">
            {sessions.length === 0 ? (
              <div className="px-3 py-6 text-center">
                <p className="text-[11px] text-text-muted leading-relaxed">
                  No conversation history yet. Start asking questions to view saved threads.
                </p>
              </div>
            ) : (
              sessions.map((session) => {
                const isActive = pathname === "/chat" && session.id === activeSessionId;
                return (
                  <div
                    key={session.id}
                    className={`group relative flex items-center justify-between rounded-xl px-2.5 py-2 transition-all ${
                      isActive
                        ? "bg-cyan/10 text-cyan border border-cyan/40 font-semibold shadow-xs"
                        : "text-text-muted hover:bg-surface-light hover:text-text-primary border border-transparent"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => handleSelectSession(session.id)}
                      className="flex min-w-0 flex-1 items-start gap-2 text-left"
                    >
                      <MessageSquare
                        size={13}
                        className={`mt-0.5 shrink-0 ${
                          isActive ? "text-cyan" : "text-text-muted group-hover:text-text-primary"
                        }`}
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-medium leading-tight">
                          {session.title || "New Inquiry"}
                        </p>
                        <span className="text-[10px] text-text-muted font-mono block mt-0.5">
                          {formatRelativeTime(session.updatedAt)}
                        </span>
                      </div>
                    </button>

                    {/* Delete button on hover */}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteSession(session.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-500/10 hover:text-red-400 text-text-muted transition-all shrink-0 ml-1"
                      title="Delete chat"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </aside>

      {/* Mobile bottom tab bar */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 h-16 bg-surface border-t border-border flex items-center justify-around z-50">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex flex-col items-center gap-1 px-2 ${
                active ? "text-cyan" : "text-text-muted"
              }`}
            >
              <Icon size={20} />
              <span className="text-[10px] font-medium">{label}</span>
            </Link>
          );
        })}
      </nav>
    </>
  );
}