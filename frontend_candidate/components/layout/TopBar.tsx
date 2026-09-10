"use client";

import { Search, Bell, User } from "lucide-react";

export default function TopBar() {
  return (
    <header className="h-16 border-b border-border bg-surface/60 backdrop-blur flex items-center justify-between px-4 md:px-6 shrink-0">
      <div className="flex items-center gap-2 md:hidden">
        <span className="font-display font-bold text-lg text-cyan tracking-wide">Oceanix</span>
      </div>

      <div className="hidden sm:flex items-center gap-2 bg-surface-light border border-border rounded-lg px-3 py-1.5 w-full max-w-xs">
        <Search size={16} className="text-text-muted" />
        <input
          type="text"
          placeholder="Search..."
          className="bg-transparent outline-none text-sm placeholder:text-text-muted w-full"
        />
      </div>

      <div className="flex items-center gap-3 md:gap-4">
        <button className="relative p-2 rounded-lg hover:bg-surface-light transition-colors">
          <Bell size={18} className="text-text-muted" />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-avoid rounded-full" />
        </button>
        <button className="w-8 h-8 rounded-full bg-surface-light border border-border flex items-center justify-center">
          <User size={16} className="text-text-muted" />
        </button>
      </div>
    </header>
  );
}