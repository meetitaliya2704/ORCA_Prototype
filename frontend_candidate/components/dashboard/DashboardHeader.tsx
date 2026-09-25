"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  MapPin,
  Sun,
  User,
  ChevronDown,
  Sparkles,
  Shield,
  Microscope,
  Anchor,
  Compass,
  LogOut,
  Bell,
  Check,
} from "lucide-react";
import { useUserMode } from "@/lib/context";
import type { UserMode } from "@/lib/types";

const PERSONAS: { id: UserMode; label: string; icon: any; description: string }[] = [
  {
    id: "fisherman",
    label: "Fisherman",
    icon: Anchor,
    description: "Coastal advisory, wave alerts & safe fishing guidance",
  },
  {
    id: "authority",
    label: "Port Authority",
    icon: Shield,
    description: "Vessel traffic surveillance, port alerts & incident response",
  },
  {
    id: "researcher",
    label: "Researcher",
    icon: Microscope,
    description: "Ocean temperature anomalies, chlorophyll & climate trends",
  },
  {
    id: "operator",
    label: "Fleet Operator",
    icon: Compass,
    description: "Commercial route optimization, fuel planning & risk avoidance",
  },
];

export default function DashboardHeader() {
  const { mode, switchRole, user, location, setLocation } = useUserMode();
  const [roleDropdownOpen, setRoleDropdownOpen] = useState(false);
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);
  const [locationModalOpen, setLocationModalOpen] = useState(false);

  const activePersona = PERSONAS.find((p) => p.id === mode) || PERSONAS[0];

  const handleSelectRole = (newRole: UserMode) => {
    switchRole(newRole);
    setRoleDropdownOpen(false);
    setUserDropdownOpen(false);
  };

  return (
    <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-200/90 shadow-2xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-3">
        {/* Left: Brand Identity */}
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="w-9 h-9 rounded-xl bg-[#0066CC]/10 border border-[#0066CC]/30 flex items-center justify-center overflow-hidden transition-transform group-hover:scale-105">
              <Image
                src="/brand/oceanix-logo.png"
                alt="Oceanix"
                width={36}
                height={36}
                className="w-full h-full object-cover scale-125"
              />
            </div>
            <div className="flex flex-col">
              <span className="font-display font-black text-lg tracking-tight text-slate-900 leading-none">
                Oceanix
              </span>
              <span className="text-[10px] font-semibold text-slate-500 tracking-wider">
                Marine Intelligence
              </span>
            </div>
          </Link>
        </div>

        {/* Center: Context & Weather Pills */}
        <div className="hidden md:flex items-center gap-2.5">
          {/* Location Badge */}
          <button
            type="button"
            onClick={() => setLocationModalOpen(!locationModalOpen)}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-slate-50 border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition-colors shadow-2xs"
          >
            <MapPin size={13} className="text-[#0066CC]" />
            <span>{location}</span>
            <span className="text-[10px] font-normal text-slate-400">· Live</span>
          </button>

          {/* Ocean Weather Badge */}
          <div className="flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-emerald-50/70 border border-emerald-200/70 text-xs font-semibold text-emerald-800 shadow-2xs">
            <Sun size={14} className="text-amber-500 shrink-0" />
            <span className="truncate max-w-[240px]">
              {mode === "fisherman" ? "Good conditions for fishing" : "Operational sea conditions"}
            </span>
          </div>
        </div>

        {/* Right Actions: Role Switcher & User Profile */}
        <div className="flex items-center gap-2.5">
          {/* Stakeholder Switcher */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setRoleDropdownOpen(!roleDropdownOpen)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-blue-50/80 border border-blue-200/80 text-xs font-bold text-[#0066CC] hover:bg-blue-100/70 transition-all shadow-2xs"
            >
              <Sparkles size={13} className="text-[#0066CC]" />
              <span className="hidden sm:inline">Role:</span>
              <span className="font-extrabold">{activePersona.label}</span>
              <ChevronDown size={13} className="opacity-70" />
            </button>

            {roleDropdownOpen && (
              <div className="absolute right-0 mt-2 w-72 bg-white rounded-2xl border border-slate-200 shadow-xl py-2 z-50 animate-in fade-in-50 zoom-in-95">
                <div className="px-3.5 py-2 border-b border-slate-100 flex items-center justify-between">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    Switch Stakeholder View
                  </span>
                </div>
                <div className="p-1 space-y-1">
                  {PERSONAS.map((p) => {
                    const Icon = p.icon;
                    const isSelected = p.id === mode;
                    return (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => handleSelectRole(p.id)}
                        className={`w-full flex items-start gap-3 p-2.5 rounded-xl text-left transition-all ${
                          isSelected
                            ? "bg-[#0066CC]/10 border border-[#0066CC]/30 text-[#0066CC]"
                            : "hover:bg-slate-50 text-slate-700 border border-transparent"
                        }`}
                      >
                        <div
                          className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                            isSelected ? "bg-[#0066CC] text-white" : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          <Icon size={16} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold">{p.label}</span>
                            {isSelected && <Check size={14} className="text-[#0066CC]" />}
                          </div>
                          <p className="text-[11px] text-slate-400 line-clamp-1">{p.description}</p>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* User Profile Pill */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setUserDropdownOpen(!userDropdownOpen)}
              className="flex items-center gap-2 pl-2 pr-3 py-1 rounded-xl bg-slate-50 border border-slate-200 hover:bg-slate-100 transition-all text-xs font-bold text-slate-800 shadow-2xs"
            >
              <div className="w-7 h-7 rounded-lg bg-[#0066CC]/15 text-[#0066CC] flex items-center justify-center font-bold">
                <User size={15} />
              </div>
              <div className="hidden sm:flex flex-col text-left leading-tight">
                <span className="font-bold text-slate-900">{user.name}</span>
                <span className="text-[10px] font-medium text-slate-500">{user.roleLabel}</span>
              </div>
              <ChevronDown size={13} className="text-slate-400" />
            </button>

            {userDropdownOpen && (
              <div className="absolute right-0 mt-2 w-56 bg-white rounded-2xl border border-slate-200 shadow-xl py-2 z-50 animate-in fade-in-50 zoom-in-95">
                <div className="px-4 py-2 border-b border-slate-100">
                  <p className="text-xs font-bold text-slate-900">{user.name}</p>
                  <p className="text-[11px] text-slate-500 truncate">{user.email}</p>
                  <span className="inline-block mt-1 text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-medium">
                    {user.roleLabel}
                  </span>
                </div>
                <div className="p-1">
                  <Link
                    href="/alerts"
                    onClick={() => setUserDropdownOpen(false)}
                    className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold text-slate-700 hover:bg-slate-50"
                  >
                    <Bell size={14} className="text-slate-500" />
                    <span>Active Advisories</span>
                  </Link>
                  <button
                    type="button"
                    onClick={() => {
                      switchRole("fisherman");
                      setUserDropdownOpen(false);
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold text-rose-600 hover:bg-rose-50 text-left"
                  >
                    <LogOut size={14} />
                    <span>Switch to Default Role</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

