"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ShieldAlert,
  Ship,
  AlertTriangle,
  Radio,
  FileText,
  Anchor,
  Compass,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  CheckCircle2,
  Clock,
  MapPin,
  Maximize2,
} from "lucide-react";
import MiniMapWidget from "./MiniMapWidget";
import { mockPortAuthorityDashboard } from "@/lib/mockData";
import { useUserMode } from "@/lib/context";

export default function PortAuthorityDashboardView() {
  const { location } = useUserMode();
  const [selectedLayer, setSelectedLayer] = useState<"weather" | "waves" | "temp" | "none">("weather");
  const data = mockPortAuthorityDashboard;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Subheader Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4.5 rounded-2xl bg-white border border-slate-200 shadow-2xs">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-50 text-[#0066CC] flex items-center justify-center font-bold">
            <Anchor size={20} />
          </div>
          <div>
            <h2 className="font-display font-black text-lg text-slate-900 leading-tight">
              ORCA — Port & Coastal Authority
            </h2>
            <p className="text-xs text-slate-500 font-medium">
              Monitor maritime operations. Respond to active distress. Keep our coastal waters safe.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-600 bg-slate-100 px-3 py-1.5 rounded-xl">
            Sector: Gujarat Coast (IMD & DGLL Grid)
          </span>
        </div>
      </div>

      {/* 4 KPI Metrics Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {/* Active Alerts */}
        <div className="p-4.5 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500">Active Alerts</span>
            <div className="w-7 h-7 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center">
              <ShieldAlert size={16} />
            </div>
          </div>
          <div className="font-display font-black text-3xl text-slate-900">
            {data.kpis[0].count}
          </div>
          <div className="flex items-center gap-1 text-[11px] font-bold text-rose-600">
            <TrendingUp size={12} />
            <span>{data.kpis[0].change}</span>
          </div>
        </div>

        {/* Vessels at Risk */}
        <div className="p-4.5 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500">Vessels at Risk</span>
            <div className="w-7 h-7 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
              <Ship size={16} />
            </div>
          </div>
          <div className="font-display font-black text-3xl text-slate-900">
            {data.kpis[1].count}
          </div>
          <div className="flex items-center gap-1 text-[11px] font-bold text-emerald-600">
            <TrendingDown size={12} />
            <span>{data.kpis[1].change}</span>
          </div>
        </div>

        {/* Incidents */}
        <div className="p-4.5 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500">Incidents</span>
            <div className="w-7 h-7 rounded-lg bg-blue-50 text-[#0066CC] flex items-center justify-center">
              <AlertTriangle size={16} />
            </div>
          </div>
          <div className="font-display font-black text-3xl text-slate-900">
            {data.kpis[2].count}
          </div>
          <div className="text-[11px] font-semibold text-slate-400">
            {data.kpis[2].change}
          </div>
        </div>

        {/* Total Vessels */}
        <div className="p-4.5 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500">Total Tracked</span>
            <div className="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <Radio size={16} />
            </div>
          </div>
          <div className="font-display font-black text-3xl text-slate-900">
            {data.kpis[3].count}
          </div>
          <div className="flex items-center gap-1 text-[11px] font-bold text-emerald-600">
            <TrendingUp size={12} />
            <span>{data.kpis[3].change}</span>
          </div>
        </div>
      </div>

      {/* Main Situation Room Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Interactive Situation Map (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          <div className="p-5 rounded-3xl bg-white border border-slate-200 shadow-2xs space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-display font-black text-base text-slate-900">
                  Live Situation Overview
                </h3>
                <p className="text-xs text-slate-500 font-medium">
                  Real-time AIS vessel telemetry & official IMD danger polygon overlay
                </p>
              </div>
              <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-xl text-xs font-bold text-slate-600">
                <button
                  type="button"
                  onClick={() => setSelectedLayer("weather")}
                  className={`px-2.5 py-1 rounded-lg transition-colors ${
                    selectedLayer === "weather" ? "bg-white text-slate-900 shadow-xs" : "hover:text-slate-900"
                  }`}
                >
                  Wind/Weather
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedLayer("waves")}
                  className={`px-2.5 py-1 rounded-lg transition-colors ${
                    selectedLayer === "waves" ? "bg-white text-slate-900 shadow-xs" : "hover:text-slate-900"
                  }`}
                >
                  Waves
                </button>
              </div>
            </div>

            <MiniMapWidget
              locationName="Gujarat Coastal Command Deck"
              center={[70.50, 21.10]}
              zoom={7.5}
              className="h-[420px]"
            />
          </div>
        </div>

        {/* Right Column: Active Alerts List & Port Status (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          {/* Active Alerts Strip */}
          <div className="p-5 rounded-3xl bg-white border border-slate-200 shadow-2xs space-y-3.5">
            <div className="flex items-center justify-between">
              <h3 className="font-display font-black text-base text-slate-900">
                Active Sector Warnings
              </h3>
              <Link href="/alerts" className="text-xs font-bold text-[#0066CC] hover:underline">
                View All →
              </Link>
            </div>

            <div className="space-y-2.5">
              {data.activeAlerts.map((alt) => (
                <div
                  key={alt.id}
                  className="p-3.5 rounded-2xl bg-slate-50 border border-slate-200 flex items-start gap-3 hover:bg-slate-100/70 transition-colors"
                >
                  <div className="w-8 h-8 rounded-xl bg-rose-100 text-rose-600 flex items-center justify-center shrink-0 mt-0.5">
                    <ShieldAlert size={16} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1">
                      <span className="font-bold text-xs text-slate-900 truncate">
                        {alt.title}
                      </span>
                      <span className="text-[10px] font-bold text-rose-600 bg-rose-50 px-2 py-0.5 rounded-full border border-rose-200 shrink-0">
                        {alt.severity}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-500 mt-0.5">{alt.location}</p>
                    <div className="flex items-center gap-1 text-[10px] text-slate-400 mt-1">
                      <Clock size={10} />
                      <span>{alt.time}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Port Operational Status */}
          <div className="p-5 rounded-3xl bg-white border border-slate-200 shadow-2xs space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-display font-black text-base text-slate-900">
                Port Clearance Status
              </h3>
              <span className="flex items-center gap-1 text-[11px] font-bold text-emerald-600 bg-emerald-50 px-2.5 py-0.5 rounded-full">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                Live
              </span>
            </div>

            <div className="space-y-2">
              {data.portStatus.map((p) => (
                <div
                  key={p.port}
                  className="p-3 rounded-xl bg-slate-50 border border-slate-200/90 flex items-center justify-between"
                >
                  <div className="flex items-center gap-2.5">
                    <Anchor size={15} className="text-slate-600" />
                    <span className="text-xs font-bold text-slate-800">{p.port}</span>
                  </div>
                  <span
                    className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full ${
                      p.tone === "go"
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : "bg-amber-50 text-amber-700 border border-amber-200"
                    }`}
                  >
                    {p.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Action Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
        <Link
          href="/map"
          className="p-3.5 rounded-2xl bg-white border border-slate-200 shadow-2xs hover:border-[#0066CC] transition-all flex items-center gap-3 font-bold text-xs text-slate-800"
        >
          <div className="w-8 h-8 rounded-lg bg-blue-50 text-[#0066CC] flex items-center justify-center">
            <Radio size={16} />
          </div>
          <span>Live AIS Radar</span>
        </Link>

        <Link
          href="/alerts"
          className="p-3.5 rounded-2xl bg-white border border-slate-200 shadow-2xs hover:border-[#0066CC] transition-all flex items-center gap-3 font-bold text-xs text-slate-800"
        >
          <div className="w-8 h-8 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center">
            <ShieldAlert size={16} />
          </div>
          <span>Broadcast Warning</span>
        </Link>

        <Link
          href="/chat"
          className="p-3.5 rounded-2xl bg-white border border-slate-200 shadow-2xs hover:border-[#0066CC] transition-all flex items-center gap-3 font-bold text-xs text-slate-800"
        >
          <div className="w-8 h-8 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
            <Compass size={16} />
          </div>
          <span>Ask AI Coordinator</span>
        </Link>

        <button
          type="button"
          onClick={() => window.print()}
          className="p-3.5 rounded-2xl bg-white border border-slate-200 shadow-2xs hover:border-[#0066CC] transition-all flex items-center gap-3 font-bold text-xs text-slate-800 text-left"
        >
          <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center">
            <FileText size={16} />
          </div>
          <span>Generate Port PDF</span>
        </button>
      </div>
    </div>
  );
}

