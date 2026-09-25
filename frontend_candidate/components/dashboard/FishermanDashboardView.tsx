"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ShieldCheck,
  ArrowRight,
  Waves,
  Wind,
  Zap,
  Thermometer,
  Info,
  Map as MapIcon,
  MessageSquareText,
  AlertOctagon,
  PhoneCall,
  CheckCircle2,
  X,
  ExternalLink,
} from "lucide-react";
import MiniMapWidget from "./MiniMapWidget";
import { mockFishermanDashboard } from "@/lib/mockData";
import { useUserMode } from "@/lib/context";

export default function FishermanDashboardView() {
  const { location } = useUserMode();
  const [emergencyModalOpen, setEmergencyModalOpen] = useState(false);
  const data = mockFishermanDashboard;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Main Grid: Left Decision & Metrics + Right Mini Map */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Decision Banner, Metrics Grid, Why Strip (7 cols) */}
        <div className="lg:col-span-7 space-y-5">
          {/* Main Decision Banner: "CAN I GO FISHING? -> GO" */}
          <div className="p-6 sm:p-7 rounded-3xl bg-white border border-slate-200/90 shadow-[0_4px_24px_rgba(0,40,80,0.06)] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-5 relative overflow-hidden">
            <div className="flex items-start gap-4 z-10">
              <div className="w-14 h-14 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-600 shrink-0 mt-0.5">
                <ShieldCheck size={32} />
              </div>
              <div className="space-y-1.5">
                <h1 className="font-display font-black text-2xl sm:text-3xl text-slate-900 tracking-tight">
                  {data.decision.headline}
                </h1>
                <p className="text-sm font-medium text-slate-600 leading-relaxed max-w-md">
                  {data.decision.description}
                </p>
              </div>
            </div>

            {/* Big Green GO Button / Badge */}
            <div className="shrink-0 w-full sm:w-auto z-10">
              <Link
                href="/map"
                className="w-full sm:w-auto px-8 py-4 rounded-2xl bg-[#059669] hover:bg-[#047857] text-white font-black text-xl tracking-wide flex items-center justify-center gap-3 shadow-lg shadow-emerald-600/25 transition-all hover:scale-[1.02] active:scale-[0.98]"
              >
                <span>→ GO</span>
              </Link>
            </div>

            {/* Subtle background glow */}
            <div className="absolute -right-8 -top-8 w-44 h-44 rounded-full bg-emerald-500/5 blur-2xl pointer-events-none" />
          </div>

          {/* 4 Core Parameter Cards (2x2 Grid) */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
            {/* Wave Height */}
            <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="w-8 h-8 rounded-xl bg-blue-50 text-[#0066CC] flex items-center justify-center">
                  <Waves size={18} />
                </div>
              </div>
              <div>
                <span className="text-xs font-semibold text-slate-500">Wave Height</span>
                <div className="font-display font-black text-2xl text-slate-900 mt-0.5">
                  1.2 m
                </div>
              </div>
              <span className="inline-block px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-50 text-blue-700 border border-blue-200/60">
                Moderate
              </span>
            </div>

            {/* Wind Speed */}
            <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="w-8 h-8 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
                  <Wind size={18} />
                </div>
              </div>
              <div>
                <span className="text-xs font-semibold text-slate-500">Wind Speed</span>
                <div className="font-display font-black text-2xl text-slate-900 mt-0.5">
                  18 km/h
                </div>
              </div>
              <span className="inline-block px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200/60">
                Favorable
              </span>
            </div>

            {/* Storm Activity */}
            <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="w-8 h-8 rounded-xl bg-slate-100 text-slate-700 flex items-center justify-center">
                  <Zap size={18} />
                </div>
              </div>
              <div>
                <span className="text-xs font-semibold text-slate-500">Storm</span>
                <div className="font-display font-black text-2xl text-slate-900 mt-0.5">
                  None
                </div>
              </div>
              <span className="inline-block px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200/60">
                No Risk
              </span>
            </div>

            {/* Sea Temperature */}
            <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="w-8 h-8 rounded-xl bg-cyan-50 text-cyan-600 flex items-center justify-center">
                  <Thermometer size={18} />
                </div>
              </div>
              <div>
                <span className="text-xs font-semibold text-slate-500">Sea Temp</span>
                <div className="font-display font-black text-2xl text-slate-900 mt-0.5">
                  28°C
                </div>
              </div>
              <span className="inline-block px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-cyan-50 text-cyan-700 border border-cyan-200/60">
                Normal
              </span>
            </div>
          </div>

          {/* "Why?" Evidence Strip */}
          <Link
            href="/why-orca"
            className="group block p-4 sm:p-4.5 rounded-2xl bg-white border border-slate-200/90 shadow-2xs hover:border-[#0066CC]/50 transition-all"
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-full bg-[#0066CC] text-white flex items-center justify-center shrink-0">
                  <Info size={15} />
                </div>
                <div>
                  <span className="font-display font-black text-sm text-slate-900 group-hover:text-[#0066CC] transition-colors">
                    Why?
                  </span>
                  <span className="text-xs text-slate-500 ml-2 font-medium">
                    {data.whyExplanation}
                  </span>
                </div>
              </div>

              {/* Source Tags */}
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {data.metrics.map((m) => (
                  <span
                    key={m.id}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-50 border border-slate-200 text-slate-700 font-medium text-[11px]"
                  >
                    <span>{m.label} {m.value}</span>
                    <span className="text-slate-400 font-bold">({m.source})</span>
                  </span>
                ))}
              </div>
            </div>
          </Link>
        </div>

        {/* Right Column: Coastal Map Widget (5 cols) */}
        <div className="lg:col-span-5">
          <MiniMapWidget locationName={location} className="h-[440px] w-full" />
        </div>
      </div>

      {/* Bottom Action Cards Bar (3 Buttons: View Map, Ask ORCA, Emergency 112) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
        {/* View Map Action */}
        <Link
          href="/map"
          className="group p-4 rounded-2xl bg-white border border-slate-200/90 shadow-2xs hover:border-[#0066CC] hover:shadow-md transition-all flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-50 text-[#0066CC] flex items-center justify-center group-hover:scale-105 transition-transform">
              <MapIcon size={20} />
            </div>
            <div>
              <span className="font-display font-black text-base text-slate-900 group-hover:text-[#0066CC] transition-colors">
                View Map
              </span>
              <p className="text-xs text-slate-500">Plan fishing trip with safe routes</p>
            </div>
          </div>
          <ArrowRight size={18} className="text-slate-400 group-hover:text-[#0066CC] group-hover:translate-x-1 transition-all" />
        </Link>

        {/* Ask ORCA Action */}
        <Link
          href="/chat"
          className="group p-4 rounded-2xl bg-white border border-slate-200/90 shadow-2xs hover:border-[#0066CC] hover:shadow-md transition-all flex items-center justify-between"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center group-hover:scale-105 transition-transform">
              <MessageSquareText size={20} />
            </div>
            <div>
              <span className="font-display font-black text-base text-slate-900 group-hover:text-purple-600 transition-colors">
                Ask ORCA
              </span>
              <p className="text-xs text-slate-500">AI advisor for instant marine questions</p>
            </div>
          </div>
          <ArrowRight size={18} className="text-slate-400 group-hover:text-purple-600 group-hover:translate-x-1 transition-all" />
        </Link>

        {/* Emergency SOS Action */}
        <button
          type="button"
          onClick={() => setEmergencyModalOpen(true)}
          className="group p-4 rounded-2xl bg-rose-50/70 border border-rose-200 shadow-2xs hover:border-rose-400 hover:bg-rose-100/60 transition-all flex items-center justify-between text-left"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-rose-500 text-white flex items-center justify-center group-hover:scale-105 transition-transform shadow-xs">
              <AlertOctagon size={20} />
            </div>
            <div>
              <span className="font-display font-black text-base text-rose-700">
                Emergency 112
              </span>
              <p className="text-xs text-rose-600/80">Coast Guard & Port Distress Contact</p>
            </div>
          </div>
          <ArrowRight size={18} className="text-rose-500 group-hover:translate-x-1 transition-all" />
        </button>
      </div>

      {/* Emergency Distress Modal */}
      {emergencyModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 border border-slate-200 shadow-2xl space-y-5">
            <div className="flex items-start justify-between">
              <div className="w-12 h-12 rounded-2xl bg-rose-100 text-rose-600 flex items-center justify-center">
                <AlertOctagon size={28} />
              </div>
              <button
                type="button"
                onClick={() => setEmergencyModalOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"
              >
                <X size={20} />
              </button>
            </div>

            <div className="space-y-2">
              <h3 className="font-display font-black text-xl text-slate-900">
                Maritime Emergency & SOS
              </h3>
              <p className="text-xs text-slate-600">
                If you or nearby vessels are experiencing distress, contact the Indian Coast Guard or Coastal Police immediately:
              </p>
            </div>

            <div className="space-y-2.5">
              <a
                href="tel:112"
                className="w-full flex items-center justify-between p-3.5 rounded-2xl bg-rose-600 text-white font-bold text-sm hover:bg-rose-700 transition-colors shadow-md"
              >
                <span className="flex items-center gap-2">
                  <PhoneCall size={18} />
                  <span>National Emergency Line</span>
                </span>
                <span className="font-black text-base">112</span>
              </a>

              <a
                href="tel:1554"
                className="w-full flex items-center justify-between p-3.5 rounded-2xl bg-slate-100 text-slate-900 font-bold text-sm hover:bg-slate-200 transition-colors"
              >
                <span className="flex items-center gap-2">
                  <PhoneCall size={18} />
                  <span>Indian Coast Guard SOS</span>
                </span>
                <span className="font-black text-base">1554</span>
              </a>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-[11px] text-slate-500 font-mono">
              GPS Position: 20° 54' 00" N, 70° 22' 00" E (Veraval Offshore)
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

