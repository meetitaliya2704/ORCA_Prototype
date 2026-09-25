"use client";

import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  ShieldCheck,
  Waves,
  Wind,
  Radio,
  Thermometer,
  ExternalLink,
  MapPin,
  ArrowRight,
  FileText,
  AlertTriangle,
  HelpCircle,
} from "lucide-react";
import MiniMapWidget from "@/components/dashboard/MiniMapWidget";
import { useUserMode } from "@/lib/context";

export default function WhyOrcaPage() {
  const { location } = useUserMode();

  return (
    <div className="min-h-screen bg-[#F8FAFC] py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-6">
        {/* Top Back Navigation */}
        <div className="flex items-center justify-between">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 text-xs font-bold text-slate-600 hover:text-[#0066CC] transition-colors bg-white px-3.5 py-2 rounded-xl border border-slate-200 shadow-2xs"
          >
            <ArrowLeft size={14} />
            <span>Back to Dashboard</span>
          </Link>

          <span className="text-xs font-semibold text-slate-500 bg-blue-50/80 text-[#0066CC] border border-blue-200 px-3 py-1.5 rounded-xl">
            Powered by Multiple Marine Sources
          </span>
        </div>

        {/* Hero Recommendation Card */}
        <div className="p-6 sm:p-8 rounded-3xl bg-white border border-slate-200 shadow-2xs flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-start gap-4">
            <div className="w-14 h-14 rounded-2xl bg-emerald-50 text-emerald-600 border border-emerald-200 flex items-center justify-center shrink-0">
              <CheckCircle2 size={32} />
            </div>
            <div className="space-y-1.5">
              <h1 className="font-display font-black text-2xl sm:text-3xl text-slate-900 tracking-tight">
                Why does ORCA say GO?
              </h1>
              <p className="text-sm font-medium text-slate-600 max-w-xl leading-relaxed">
                Yes, it is safe to go fishing today from {location}. Weather and ocean conditions are favorable with low risk. ORCA analyzed 4 independent marine data sources to reach this recommendation.
              </p>
            </div>
          </div>

          <div className="flex flex-col items-center justify-center p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-center shrink-0 min-w-[160px]">
            <span className="font-display font-black text-2xl text-emerald-700 tracking-wide">
              GO
            </span>
            <span className="text-xs font-bold text-emerald-800 mt-0.5">
              Confidence: High (87%)
            </span>
          </div>
        </div>

        {/* Main Grid: Evidence Cards + Side Summary */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: 4 Detailed Evidence Cards (8 cols) */}
          <div className="lg:col-span-8 space-y-4">
            <h2 className="font-display font-black text-lg text-slate-900">
              Evidence from Multiple Sources
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Card 1: Weather Forecast (IMD) */}
              <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-xl bg-blue-50 text-[#0066CC] flex items-center justify-center">
                      <Wind size={18} />
                    </div>
                    <span className="font-bold text-sm text-slate-900">Weather Forecast</span>
                  </div>
                  <span className="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200">
                    Favorable
                  </span>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed font-medium">
                  Wind and wave conditions are favorable (1.2 m waves, 18 km/h wind) for safe fishing in the next 24 hours.
                </p>
                <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400 font-medium">
                  <span>Source: IMD</span>
                  <span>Updated 5 min ago</span>
                </div>
              </div>

              {/* Card 2: Ocean Model (INCOIS) */}
              <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-xl bg-cyan-50 text-cyan-600 flex items-center justify-center">
                      <Waves size={18} />
                    </div>
                    <span className="font-bold text-sm text-slate-900">Ocean Model</span>
                  </div>
                  <span className="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200">
                    No Major Risk
                  </span>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed font-medium">
                  No storm or cyclone activity detected in the active coastal polygon. Ocean hydrodynamic conditions are stable.
                </p>
                <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400 font-medium">
                  <span>Source: INCOIS</span>
                  <span>Updated 6 min ago</span>
                </div>
              </div>

              {/* Card 3: AIS Data */}
              <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center">
                      <Radio size={18} />
                    </div>
                    <span className="font-bold text-sm text-slate-900">AIS Traffic</span>
                  </div>
                  <span className="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200">
                    Normal Activity
                  </span>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed font-medium">
                  Nearby fishing vessel movement is normal. Zero distress broadcasts or coastal patrol blocks recorded.
                </p>
                <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400 font-medium">
                  <span>Source: DGLL AIS</span>
                  <span>Updated 3 min ago</span>
                </div>
              </div>

              {/* Card 4: Sea Surface Temperature */}
              <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-2xs space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center">
                      <Thermometer size={18} />
                    </div>
                    <span className="font-bold text-sm text-slate-900">Sea Surface Data</span>
                  </div>
                  <span className="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200">
                    Normal
                  </span>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed font-medium">
                  Sea surface temperature is 28°C, well within optimal historical range for pelagic fish concentration.
                </p>
                <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400 font-medium">
                  <span>Source: SST Satellite</span>
                  <span>Updated 8 min ago</span>
                </div>
              </div>
            </div>

            {/* Overall Confidence Bar */}
            <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-2xs flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="text-xs font-bold text-slate-500">Overall Confidence:</div>
                <span className="px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-extrabold text-xs">
                  High (87%)
                </span>
              </div>
              <span className="text-xs text-slate-500 font-medium hidden sm:inline">
                All 4 deterministic safety gates passed
              </span>
            </div>
          </div>

          {/* Right Column: Mini Map & Related Actions (4 cols) */}
          <div className="lg:col-span-4 space-y-4">
            <MiniMapWidget locationName={location} className="min-h-[280px]" />

            {/* Quick Summary Strip */}
            <div className="p-5 rounded-3xl bg-white border border-slate-200 shadow-2xs space-y-3">
              <h3 className="font-display font-black text-sm text-slate-900">
                Quick Summary
              </h3>
              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between py-1 border-b border-slate-100">
                  <span className="text-slate-500">Wave Height</span>
                  <strong className="text-slate-900">1.2 m (Moderate)</strong>
                </div>
                <div className="flex items-center justify-between py-1 border-b border-slate-100">
                  <span className="text-slate-500">Wind Speed</span>
                  <strong className="text-slate-900">18 km/h (Favorable)</strong>
                </div>
                <div className="flex items-center justify-between py-1 border-b border-slate-100">
                  <span className="text-slate-500">Storm Activity</span>
                  <strong className="text-emerald-600">None (No Risk)</strong>
                </div>
                <div className="flex items-center justify-between py-1">
                  <span className="text-slate-500">Sea Temperature</span>
                  <strong className="text-slate-900">28°C (Normal)</strong>
                </div>
              </div>
            </div>

            {/* Related Actions */}
            <div className="p-5 rounded-3xl bg-white border border-slate-200 shadow-2xs space-y-2.5">
              <h3 className="font-display font-black text-sm text-slate-900 mb-2">
                Related Actions
              </h3>
              <Link
                href="/map"
                className="w-full flex items-center justify-between p-2.5 rounded-xl hover:bg-slate-50 text-xs font-bold text-slate-800 transition-colors"
              >
                <span>View on Map</span>
                <ArrowRight size={14} className="text-[#0066CC]" />
              </Link>
              <Link
                href="/chat"
                className="w-full flex items-center justify-between p-2.5 rounded-xl hover:bg-slate-50 text-xs font-bold text-slate-800 transition-colors"
              >
                <span>Ask ORCA another question</span>
                <ArrowRight size={14} className="text-purple-600" />
              </Link>
              <Link
                href="/alerts"
                className="w-full flex items-center justify-between p-2.5 rounded-xl hover:bg-slate-50 text-xs font-bold text-slate-800 transition-colors"
              >
                <span>Check latest alerts</span>
                <ArrowRight size={14} className="text-rose-600" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

