"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Compass,
  Ship,
  Fuel,
  Navigation,
  CheckCircle2,
  Clock,
  ArrowRight,
  TrendingDown,
  AlertTriangle,
  MapPin,
  ShieldCheck,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import MiniMapWidget from "./MiniMapWidget";
import { mockFleetOperatorDashboard } from "@/lib/mockData";

export default function FleetOperatorDashboardView() {
  const [fromPort, setFromPort] = useState("Veraval, Gujarat");
  const [toPort, setToPort] = useState("Mumbai, Maharashtra");
  const [vesselType, setVesselType] = useState("Commercial Trawler / Longliner");
  const [isCalculating, setIsCalculating] = useState(false);
  const [routeSummary, setRouteSummary] = useState(mockFleetOperatorDashboard.routeSummary);
  const [routeComparison, setRouteComparison] = useState(mockFleetOperatorDashboard.routeComparison);
  const [calculationFeedback, setCalculationFeedback] = useState<string | null>(null);

  const handleRecalculate = () => {
    setIsCalculating(true);
    setCalculationFeedback(null);

    setTimeout(() => {
      // Deterministically derive values based on selected ports and vessel
      const isLongVoyage = toPort.toLowerCase().includes("cochin") || toPort.toLowerCase().includes("chennai");
      const isGoa = toPort.toLowerCase().includes("goa") || toPort.toLowerCase().includes("mangalore");
      
      const distanceNM = isLongVoyage ? 840 : isGoa ? 495 : 312;
      const hours = Math.round(distanceNM / 14.5 * 10) / 10;
      const fuelPerNm = vesselType.includes("Cargo") ? 18.5 : vesselType.includes("OSV") ? 14.2 : 9.8;
      const fuelTotal = Math.round(distanceNM * fuelPerNm);
      const directFuel = Math.round(fuelTotal * 1.14);
      const directHours = Math.round((hours + 3.2) * 10) / 10;

      setRouteSummary({
        from: fromPort,
        to: toPort,
        risk: "OPTIMAL (LOW)",
        eta: `${hours} Hours`,
        distance: `${distanceNM} Nautical Miles (~${Math.round(distanceNM * 1.852)} km)`,
        weather: "Moderate westerly swell (1.4m - 1.8m), Wind: SW 14 kts",
        fuelEstimate: `${fuelTotal.toLocaleString()} Liters (Detour saves ~14% vs high-risk headseas)`,
        alternativeNote: "Hydrodynamically optimized corridor bypassing coastal shallow shoals",
      });

      setRouteComparison([
        {
          parameter: "Transit Distance",
          selected: `${distanceNM} NM (via Navigational Corridor)`,
          alternative: `${distanceNM - 22} NM (Direct High-Risk)`,
        },
        {
          parameter: "Estimated Duration",
          selected: `${hours} Hours (Smooth seas)`,
          alternative: `${directHours} Hours (Heavy Pitch & Roll)`,
        },
        {
          parameter: "Fuel Consumption",
          selected: `${fuelTotal.toLocaleString()} L (Optimal RPM)`,
          alternative: `${directFuel.toLocaleString()} L (+14% Resistance)`,
        },
        {
          parameter: "IMD Hazard Intersections",
          selected: "0 Hazard Zones (Full Clearance)",
          alternative: "2 Squall Warning Corridors Active",
        },
        {
          parameter: "Weather Safety Margin",
          selected: "Within Recommended Operational Limits",
          alternative: "Risk of Slamming & Structural Fatigue",
        },
      ]);

      setIsCalculating(false);
      setCalculationFeedback(
        `Optimized corridor solved for ${fromPort.split(",")[0]} → ${toPort.split(",")[0]} (${vesselType.split("/")[0].trim()})`
      );
    }, 650);
  };

  const data = mockFleetOperatorDashboard;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Subheader Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4.5 rounded-2xl bg-white border border-slate-200 shadow-2xs">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-50 text-[#0066CC] flex items-center justify-center font-bold">
            <Compass size={20} />
          </div>
          <div>
            <h2 className="font-display font-black text-lg text-slate-900 leading-tight">
              Oceanix — Commercial Fleet Operator
            </h2>
            <p className="text-xs text-slate-500 font-medium">
              Vessel tracking, voyage cost comparison, weather-optimal routing & fuel optimization.
            </p>
          </div>
        </div>

        {/* 3 Top KPIs */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs font-semibold text-emerald-800">
            <CheckCircle2 size={14} className="text-emerald-600" />
            <span>Fleet Status: <strong>{data.kpis.status}</strong></span>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50 border border-slate-200 text-xs font-semibold text-slate-700">
            <Ship size={14} className="text-[#0066CC]" />
            <span>Vessels: <strong>{data.kpis.totalVessels}</strong></span>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50 border border-slate-200 text-xs font-semibold text-slate-700">
            <Fuel size={14} className="text-amber-600" />
            <span>Avg Fuel: <strong>{data.kpis.avgFuel}</strong></span>
          </div>
        </div>
      </div>

      {/* Main Section: Route Planner Form & Interactive Route Map */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Route Planner Form (4 cols) */}
        <div className="lg:col-span-4 p-5 rounded-3xl bg-white border border-slate-200 shadow-2xs space-y-4">
          <div>
            <h3 className="font-display font-black text-base text-slate-900">
              Plan Maritime Route
            </h3>
            <p className="text-xs text-slate-500 font-medium">
              Calculate lowest risk and optimal fuel consumption path
            </p>
          </div>

          <div className="space-y-3 pt-1">
            <div className="space-y-1">
              <label className="text-[11px] font-bold text-slate-600 uppercase tracking-wider">
                Origin Port
              </label>
              <div className="relative">
                <MapPin size={15} className="absolute left-3 top-3 text-slate-400" />
                <input
                  type="text"
                  value={fromPort}
                  onChange={(e) => setFromPort(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-xs font-bold text-slate-800 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0066CC]"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-[11px] font-bold text-slate-600 uppercase tracking-wider">
                Destination Port
              </label>
              <div className="relative">
                <Navigation size={15} className="absolute left-3 top-3 text-[#0066CC]" />
                <input
                  type="text"
                  value={toPort}
                  onChange={(e) => setToPort(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-xs font-bold text-slate-800 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0066CC]"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-[11px] font-bold text-slate-600 uppercase tracking-wider">
                Vessel Classification
              </label>
              <select
                value={vesselType}
                onChange={(e) => setVesselType(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs font-bold text-slate-800 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0066CC]"
              >
                <option>Commercial Trawler / Longliner</option>
                <option>Coastal Cargo Feeder (1000 DWT)</option>
                <option>Offshore Supply Vessel (OSV)</option>
                <option>Deep-Sea Purse Seiner</option>
              </select>
            </div>

            <button
              type="button"
              onClick={handleRecalculate}
              disabled={isCalculating}
              className="w-full py-3 rounded-xl bg-[#0066CC] hover:bg-[#0052A3] disabled:opacity-75 text-white font-bold text-xs shadow-md transition-all flex items-center justify-center gap-2 mt-2"
            >
              {isCalculating ? (
                <>
                  <RefreshCw size={14} className="animate-spin" />
                  <span>Computing Hydrodynamic Route...</span>
                </>
              ) : (
                <>
                  <span>Recalculate Optimal Route</span>
                  <ArrowRight size={14} />
                </>
              )}
            </button>
          </div>

          {/* Recalculation Confirmation Alert */}
          {calculationFeedback && (
            <div className="p-3 rounded-2xl bg-emerald-50 border border-emerald-200/90 flex items-start gap-2.5 text-xs text-emerald-900 animate-in fade-in-50">
              <Sparkles size={16} className="text-emerald-600 shrink-0 mt-0.5" />
              <div className="flex-1 font-medium leading-tight">
                <span className="font-bold block">Route Solved:</span>
                <span className="text-[11px] text-emerald-800">{calculationFeedback}</span>
              </div>
            </div>
          )}

          {/* Quick Route Specs */}
          <div className="p-3.5 rounded-2xl bg-slate-50 border border-slate-200/90 space-y-2 text-xs">
            <div className="flex items-center justify-between text-slate-600">
              <span>Estimated Distance:</span>
              <strong className="text-slate-900">{routeSummary.distance}</strong>
            </div>
            <div className="flex items-center justify-between text-slate-600">
              <span>Expected Weather:</span>
              <strong className="text-slate-900">{routeSummary.weather}</strong>
            </div>
            <div className="flex items-center justify-between text-slate-600">
              <span>Fuel Requirement:</span>
              <strong className="text-slate-900">{routeSummary.fuelEstimate}</strong>
            </div>
          </div>
        </div>

        {/* Right Column: Route Map Visualization (8 cols) */}
        <div className="lg:col-span-8 p-5 rounded-3xl bg-white border border-slate-200 shadow-2xs space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-display font-black text-base text-slate-900">
                Route Trajectory & Hazard Avoidance Corridor
              </h3>
              <p className="text-xs text-slate-500 font-medium">
                Live waypoint detour avoiding coastal swell and squall caution zones
              </p>
            </div>
            <span className="text-xs font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-full flex items-center gap-1.5">
              <ShieldCheck size={14} />
              <span>Corridor Clear & Solved</span>
            </span>
          </div>

          <MiniMapWidget
            locationName={`${fromPort.split(",")[0]} → ${toPort.split(",")[0]} Corridor`}
            center={[71.50, 20.00]}
            zoom={6.5}
            className="h-[420px]"
          />
        </div>
      </div>

      {/* Lower Section: Route Comparison Matrix & History */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Route Comparison Matrix (7 cols) */}
        <div className="lg:col-span-7 p-5 rounded-3xl bg-white border border-slate-200 shadow-2xs space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-display font-black text-base text-slate-900">
              Route Tradeoff Analysis
            </h3>
            <span className="text-[11px] text-slate-500 font-medium">
              Deterministic Oceanix Hydrodynamic Engine
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                  <th className="py-2.5 px-3">Parameter</th>
                  <th className="py-2.5 px-3 bg-blue-50/70 text-[#0066CC] font-bold rounded-t-xl">
                    Selected Route (Recommended)
                  </th>
                  <th className="py-2.5 px-3 text-slate-600">
                    Alternative Direct Route
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {routeComparison.map((row) => (
                  <tr key={row.parameter}>
                    <td className="py-3 px-3 font-semibold text-slate-700">
                      {row.parameter}
                    </td>
                    <td className="py-3 px-3 bg-blue-50/40 font-bold text-slate-900">
                      {row.selected}
                    </td>
                    <td className="py-3 px-3 text-slate-600">
                      {row.alternative}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent Routes Table (5 cols) */}
        <div className="lg:col-span-5 p-5 rounded-3xl bg-white border border-slate-200 shadow-2xs space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-display font-black text-base text-slate-900">
              Recent Fleet Voyages
            </h3>
            <span className="text-xs font-bold text-[#0066CC] hover:underline cursor-pointer">
              Log Archive →
            </span>
          </div>

          <div className="space-y-2">
            {data.recentRoutes.map((r, i) => (
              <div
                key={i}
                className="p-3 rounded-xl bg-slate-50 border border-slate-200/90 flex items-center justify-between"
              >
                <div>
                  <span className="text-xs font-bold text-slate-900 block">{r.route}</span>
                  <span className="text-[10px] text-slate-400">{r.date}</span>
                </div>
                <span
                  className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                    r.tone === "go"
                      ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                      : "bg-amber-50 text-amber-700 border border-amber-200"
                  }`}
                >
                  {r.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

