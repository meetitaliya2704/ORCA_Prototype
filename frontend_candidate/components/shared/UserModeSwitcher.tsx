"use client";

import { useUserMode } from "@/lib/context";
import { UserMode } from "@/lib/types";
import { userModeConfigs } from "@/lib/mockData";
import { Anchor, ShieldAlert, Microscope, Compass, Check } from "lucide-react";
import { useState, useRef, useEffect } from "react";

const icons = {
  fisherman: Anchor,
  authority: ShieldAlert,
  researcher: Microscope,
  operator: Compass,
};

export default function UserModeSwitcher() {
  const { mode, setMode } = useUserMode();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const activeConfig = userModeConfigs[mode] || userModeConfigs.fisherman;
  const ActiveIcon = icons[mode] || Anchor;

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-light hover:bg-surface border border-border transition-all text-xs font-medium text-text-primary"
      >
        <div className="w-5 h-5 rounded-full bg-cyan/10 border border-cyan/30 flex items-center justify-center text-cyan">
          <ActiveIcon size={12} />
        </div>
        <span className="font-medium hidden sm:inline text-text-muted">Persona:</span>
        <span className="text-cyan font-semibold">{activeConfig.label}</span>
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-72 bg-surface border border-border rounded-xl shadow-2xl z-50 p-2 space-y-1 backdrop-blur-md">
          <div className="px-2 py-1.5 border-b border-border/50 text-[11px] font-semibold text-text-muted uppercase tracking-wider">
            Switch Persona Context
          </div>
          {(Object.keys(userModeConfigs) as UserMode[]).map((key) => {
            const config = userModeConfigs[key];
            const Icon = icons[key];
            const isSelected = mode === key;

            return (
              <button
                key={key}
                onClick={() => {
                  setMode(key);
                  setIsOpen(false);
                }}
                className={`w-full flex items-start gap-3 p-2.5 rounded-lg text-left transition-colors ${
                  isSelected
                    ? "bg-surface-light border border-cyan/30"
                    : "hover:bg-surface-light/60 border border-transparent"
                }`}
              >
                <div
                  className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5 ${
                    isSelected
                      ? "bg-cyan text-bg font-bold"
                      : "bg-surface-light border border-border text-text-muted"
                  }`}
                >
                  <Icon size={14} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span
                      className={`text-xs font-semibold ${
                        isSelected ? "text-cyan" : "text-text-primary"
                      }`}
                    >
                      {config.label}
                    </span>
                    {isSelected && <Check size={14} className="text-cyan" />}
                  </div>
                  <p className="text-[11px] text-text-muted leading-snug mt-0.5 line-clamp-2">
                    {config.roleDescription}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}