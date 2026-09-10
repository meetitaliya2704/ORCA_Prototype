"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageSquareText, Map as MapIcon, Bell } from "lucide-react";

const navItems = [
  { href: "/chat", label: "AI Chat", icon: MessageSquareText },
  { href: "/map", label: "Map", icon: MapIcon },
  { href: "/alerts", label: "Alerts", icon: Bell },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <>
      {/* Desktop / tablet sidebar */}
      <aside className="hidden md:flex md:flex-col w-16 lg:w-56 bg-surface border-r border-border shrink-0">
        <div className="flex items-center gap-2 px-4 h-12 border-b border-border text-[11px] font-semibold uppercase tracking-wider text-text-muted">
          <span className="hidden lg:block">Console Deck</span>
        </div>

        <nav className="flex-1 py-4 flex flex-col gap-1 px-2">
          {navItems.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                  active
                    ? "bg-surface-light text-cyan"
                    : "text-text-muted hover:bg-surface-light hover:text-text-primary"
                }`}
              >
                <Icon size={20} className="shrink-0" />
                <span className="hidden lg:block text-sm font-medium">{label}</span>
              </Link>
            );
          })}
        </nav>
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