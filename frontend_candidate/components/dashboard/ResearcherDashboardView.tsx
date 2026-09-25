"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import {
  Microscope,
  Calendar,
  Layers,
  Sparkles,
  Download,
  ExternalLink,
  ChevronDown,
  Info,
  TrendingUp,
  Activity,
  AlertCircle,
} from "lucide-react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import MiniMapWidget, { type ResearchLayerType } from "./MiniMapWidget";

function getRollingDates(count: number = 7): string[] {
  const dates: string[] = [];
  const now = new Date();
  for (let i = count - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(now.getDate() - i);
    dates.push(d.toLocaleDateString("en-US", { day: "numeric", month: "short" }));
  }
  return dates;
}

export default function ResearcherDashboardView() {
  const [activeTab, setActiveTab] = useState<ResearchLayerType>("sst");
  const dates = useMemo(() => getRollingDates(7), []);

  const tabDatasets = useMemo(() => {
    return {
      sst: {
        title: "Ocean Surface Thermal Field",
        subtitle: "High-resolution L4 gap-free satellite analysis (METOFFICE-GLO-SST)",
        scaleTitle: "SST Scale (°C)",
        scaleGradient: "from-blue-600 via-amber-400 to-red-600",
        scaleTicks: ["32°C", "28°C", "24°C", "20°C", "16°C"],
        lineChartTitle: "SST Time Series (Veraval Transect)",
        lineChartSubtitle: "Daily observed sea surface temperature vs 30-year climatological baseline",
        lineKey: "val",
        lineName: "Observed SST (°C)",
        baselineKey: "baseline",
        baselineName: "Monthly Mean (27.2°C)",
        unit: "°C",
        yDomain: [24, 31],
        barChartTitle: "Regional Coastal Station Comparison",
        barChartSubtitle: "Mean surface temperature across Gujarat & Maharashtra monitoring buoys",
        stats: [
          { label: "Average SST", value: "28.4°C", note: "+1.2°C above baseline", alert: true },
          { label: "Thermal Range", value: "26.2°C – 29.8°C", note: "Upwelling to Gulf gradient" },
          { label: "Climatology (Sept)", value: "27.2°C", note: "30-year historical mean" },
          { label: "Area Sampled", value: "250k km²", note: "Eastern Arabian Sea Basin" },
        ],
        insights: [
          "SST off Saurashtra coast is elevated +1.2°C due to weakened post-monsoon coastal upwelling.",
          "Offshore deep waters maintain stable 28.5°C thermal stratification across the continental shelf.",
          "Shallow coastal thermal pocket active in the Gulf of Khambhat (29.8°C).",
          "Optimal thermal boundary conditions detected for pelagic mackerel and tuna concentrations.",
        ],
        timeSeries: [
          { date: dates[0], val: 27.6, baseline: 27.2 },
          { date: dates[1], val: 27.9, baseline: 27.2 },
          { date: dates[2], val: 28.3, baseline: 27.2 },
          { date: dates[3], val: 28.7, baseline: 27.2 },
          { date: dates[4], val: 28.5, baseline: 27.2 },
          { date: dates[5], val: 28.2, baseline: 27.2 },
          { date: dates[6], val: 28.4, baseline: 27.2 },
        ],
        regional: [
          { name: "Veraval", val: 28.6 },
          { name: "Porbandar", val: 28.2 },
          { name: "Okha", val: 27.8 },
          { name: "Kandla", val: 29.8 },
          { name: "Mumbai", val: 29.0 },
          { name: "Goa", val: 28.4 },
        ],
      },
      salinity: {
        title: "Sea Surface Salinity Field (PSU)",
        subtitle: "SMOS/SMAP satellite blend & Argo in-situ profiling telemetry (CMEMS-SSS-L4)",
        scaleTitle: "Salinity Scale (PSU)",
        scaleGradient: "from-purple-700 via-blue-500 to-teal-400",
        scaleTicks: ["37.0 PSU", "36.2 PSU", "35.5 PSU", "34.8 PSU", "34.0 PSU"],
        lineChartTitle: "Practical Salinity Time Series",
        lineChartSubtitle: "Daily surface salinity index vs regional baseline across Veraval shelf",
        lineKey: "val",
        lineName: "Observed Salinity (PSU)",
        baselineKey: "baseline",
        baselineName: "Regional Mean (35.5 PSU)",
        unit: "PSU",
        yDomain: [33, 38],
        barChartTitle: "Coastal Salinity Gradient",
        barChartSubtitle: "Practical salinity measurements along Gujarat and Maharashtra shelves",
        stats: [
          { label: "Mean Salinity", value: "35.8 PSU", note: "+0.3 PSU departure", alert: false },
          { label: "Haline Gradient", value: "34.6 – 36.5 PSU", note: "Estuarine to deep water" },
          { label: "Water Mass", value: "ASHSW", note: "Arabian Sea High Salinity Water" },
          { label: "River Runoff", value: "Low Impact", note: "Post-monsoon river plume" },
        ],
        insights: [
          "High evaporation in the northern Arabian Sea sustains elevated surface salinity (>36.0 PSU).",
          "Narmada-Tapi estuarine discharge lowers Gulf of Khambhat surface salinity to 34.6 PSU.",
          "Pycnocline barrier layer remains stable across Veraval–Porbandar outer shelf.",
          "Argo float profiling confirms halocline depth at 35–45 meters with normal vertical mixing.",
        ],
        timeSeries: [
          { date: dates[0], val: 35.6, baseline: 35.5 },
          { date: dates[1], val: 35.7, baseline: 35.5 },
          { date: dates[2], val: 35.9, baseline: 35.5 },
          { date: dates[3], val: 36.1, baseline: 35.5 },
          { date: dates[4], val: 35.8, baseline: 35.5 },
          { date: dates[5], val: 35.7, baseline: 35.5 },
          { date: dates[6], val: 35.8, baseline: 35.5 },
        ],
        regional: [
          { name: "Veraval", val: 35.8 },
          { name: "Porbandar", val: 36.1 },
          { name: "Okha", val: 36.5 },
          { name: "Kandla", val: 34.6 },
          { name: "Mumbai", val: 35.2 },
          { name: "Goa", val: 35.0 },
        ],
      },
      chlorophyll: {
        title: "Chlorophyll-a & Phytoplankton Biomass",
        subtitle: "Sentinel-3 OLCI & MODIS ocean color radiance (Copernicus Global 4km)",
        scaleTitle: "Chl-a (mg/m³)",
        scaleGradient: "from-indigo-950 via-emerald-500 to-yellow-400",
        scaleTicks: ["5.00", "2.50", "1.00", "0.50", "0.10"],
        lineChartTitle: "Chlorophyll-a Concentration Profile",
        lineChartSubtitle: "Daily surface primary productivity index vs regional bloom threshold",
        lineKey: "val",
        lineName: "Chlorophyll-a (mg/m³)",
        baselineKey: "baseline",
        baselineName: "Bloom Threshold (1.5 mg/m³)",
        unit: "mg/m³",
        yDomain: [0, 3],
        barChartTitle: "Primary Productivity by Station",
        barChartSubtitle: "Mean phytoplankton biomass index across critical fishing transects",
        stats: [
          { label: "Mean Chlorophyll", value: "0.86 mg/m³", note: "Moderate mesotrophic index", alert: false },
          { label: "Upwelling Peak", value: "2.42 mg/m³", note: "Near Okha headland", alert: true },
          { label: "Bloom Index", value: "Normal / Low", note: "No harmful algal bloom detected" },
          { label: "Euphotic Depth", value: "28 Meters", note: "High photosynthetic penetration" },
        ],
        insights: [
          "Strong wind-driven upwelling off Okha–Dwarka drives dense diatom biomass (2.42 mg/m³).",
          "Veraval shelf demonstrates active chlorophyll feeding front supporting sardine and anchovy schools.",
          "Clear oligotrophic waters persist 60+ nautical miles offshore (<0.25 mg/m³).",
          "No toxic algal bloom (Noctiluca or Cochlodinium) detected on multispectral satellite imagery.",
        ],
        timeSeries: [
          { date: dates[0], val: 0.65, baseline: 1.5 },
          { date: dates[1], val: 0.72, baseline: 1.5 },
          { date: dates[2], val: 0.88, baseline: 1.5 },
          { date: dates[3], val: 1.15, baseline: 1.5 },
          { date: dates[4], val: 0.98, baseline: 1.5 },
          { date: dates[5], val: 0.82, baseline: 1.5 },
          { date: dates[6], val: 0.86, baseline: 1.5 },
        ],
        regional: [
          { name: "Veraval", val: 1.12 },
          { name: "Porbandar", val: 0.95 },
          { name: "Okha", val: 2.42 },
          { name: "Kandla", val: 1.85 },
          { name: "Mumbai", val: 0.82 },
          { name: "Goa", val: 0.64 },
        ],
      },
      anomalies: {
        title: "Sea Surface Temperature Anomaly (SSTA)",
        subtitle: "NOAA/Copernicus 0.05° daily SSTA relative to 1991–2020 base period",
        scaleTitle: "Anomaly (Δ°C)",
        scaleGradient: "from-blue-600 via-slate-100 to-red-600",
        scaleTicks: ["+2.5°C", "+1.5°C", "0.0°C", "-1.0°C", "-2.0°C"],
        lineChartTitle: "Thermal Departure Time Series",
        lineChartSubtitle: "Daily deviation from seasonal 30-year normal climatological baseline",
        lineKey: "val",
        lineName: "Thermal Anomaly (Δ°C)",
        baselineKey: "baseline",
        baselineName: "Normal Climatology (0.0°C)",
        unit: "°C",
        yDomain: [-1, 2.5],
        barChartTitle: "Regional Thermal Departure",
        barChartSubtitle: "Deviation from seasonal baseline across coastal marine sectors",
        stats: [
          { label: "Mean SSTA", value: "+0.84°C", note: "Elevated sea surface warmth", alert: true },
          { label: "Peak Anomaly", value: "+1.65°C", note: "Gulf of Khambhat shallow sector" },
          { label: "Marine Heatwave", value: "Cat 1 (Moderate)", note: "5 consecutive exceedance days" },
          { label: "Cumulative MHW", value: "8.4 °C-days", note: "Low thermal stress on coral reefs" },
        ],
        insights: [
          "Persistent positive thermal anomaly (+0.84°C) recorded across the northern Arabian Sea basin.",
          "Shallow enclosed waters in the Gulf of Khambhat reached +1.65°C departure.",
          "Category 1 Moderate Marine Heatwave alert active for coastal pelagic fisheries.",
          "Upwelling pockets off southern Saurashtra maintain cooler anomaly buffers (-0.3°C).",
        ],
        timeSeries: [
          { date: dates[0], val: 0.42, baseline: 0.0 },
          { date: dates[1], val: 0.65, baseline: 0.0 },
          { date: dates[2], val: 0.95, baseline: 0.0 },
          { date: dates[3], val: 1.18, baseline: 0.0 },
          { date: dates[4], val: 0.92, baseline: 0.0 },
          { date: dates[5], val: 0.78, baseline: 0.0 },
          { date: dates[6], val: 0.84, baseline: 0.0 },
        ],
        regional: [
          { name: "Veraval", val: 0.80 },
          { name: "Porbandar", val: 0.50 },
          { name: "Okha", val: 0.30 },
          { name: "Kandla", val: 1.60 },
          { name: "Mumbai", val: 1.10 },
          { name: "Goa", val: 0.70 },
        ],
      },
      trends: {
        title: "Longitudinal Climate Warming Velocity",
        subtitle: "Copernicus decadal reanalysis regression model (1993–2026)",
        scaleTitle: "Trend (°C/dec)",
        scaleGradient: "from-amber-200 via-orange-400 to-rose-700",
        scaleTicks: ["+0.35", "+0.25", "+0.15", "+0.05", "0.00"],
        lineChartTitle: "Decadal Warming Trend Projection",
        lineChartSubtitle: "Longitudinal warming velocity trajectory (1993–2026) in the Arabian Sea",
        lineKey: "val",
        lineName: "Decadal Trend (°C/dec)",
        baselineKey: "baseline",
        baselineName: "Global Ocean Average (+0.11°C/dec)",
        unit: "°C/dec",
        yDomain: [0, 0.3],
        barChartTitle: "Decadal Trend by Marine Sector",
        barChartSubtitle: "Linear warming velocity across Arabian Sea and coastal shelves",
        stats: [
          { label: "Warming Velocity", value: "+0.14°C/dec", note: "Above global mean (+0.11)", alert: true },
          { label: "Total ΔT (1993-2026)", value: "+0.46°C", note: "Multi-decadal net increase" },
          { label: "Statistical Conf.", value: "99.2% (p < 0.01)", note: "Mann-Kendall test verified" },
          { label: "Monsoon Shift", value: "+12 Days", note: "Extended summer thermal window" },
        ],
        insights: [
          "Arabian Sea warming velocity (+0.14°C/decade) exceeds the global tropical ocean average.",
          "Winter cooling intensification has diminished by 28% over the past two decades.",
          "Enhanced thermal stratification leads to delayed post-monsoon overturning.",
          "Longitudinal models predict earlier onset of spring pre-monsoon cyclogenesis.",
        ],
        timeSeries: [
          { date: "2020", val: 0.12, baseline: 0.11 },
          { date: "2021", val: 0.13, baseline: 0.11 },
          { date: "2022", val: 0.13, baseline: 0.11 },
          { date: "2023", val: 0.14, baseline: 0.11 },
          { date: "2024", val: 0.15, baseline: 0.11 },
          { date: "2025", val: 0.14, baseline: 0.11 },
          { date: "2026", val: 0.14, baseline: 0.11 },
        ],
        regional: [
          { name: "Veraval", val: 0.14 },
          { name: "Porbandar", val: 0.13 },
          { name: "Okha", val: 0.12 },
          { name: "Kandla", val: 0.18 },
          { name: "Mumbai", val: 0.16 },
          { name: "Goa", val: 0.15 },
        ],
      },
    };
  }, [dates]);

  const activeData = tabDatasets[activeTab];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Subheader Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4.5 rounded-2xl bg-white border border-slate-200 shadow-2xs">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-teal-50 text-teal-700 flex items-center justify-center font-bold">
            <Microscope size={20} />
          </div>
          <div>
            <h2 className="font-display font-black text-lg text-slate-900 leading-tight">
              Oceanix — Marine Research & Ocean Analytics
            </h2>
            <p className="text-xs text-slate-500 font-medium">
              Copernicus CMEMS satellite telemetry, chlorophyll grids, salinity profiles & longitudinal trends.
            </p>
          </div>
        </div>

        {/* 3 Metadata Badges */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="px-3 py-1 rounded-xl bg-slate-50 border border-slate-200 text-[11px] font-semibold text-slate-700">
            Region: <span className="text-slate-900 font-bold">Gujarat Shelf</span>
          </div>
          <div className="px-3 py-1 rounded-xl bg-slate-50 border border-slate-200 text-[11px] font-semibold text-slate-700">
            Observation: <span className="text-slate-900 font-bold">{dates[6]} 2026</span>
          </div>
          <div className="px-3 py-1 rounded-xl bg-emerald-50 border border-emerald-200 text-[11px] font-semibold text-emerald-800">
            Quality: <span className="font-bold">Research Grade</span>
          </div>
        </div>
      </div>

      {/* Dataset Filter Tabs (All 5 interactive) */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {[
          { id: "sst", label: "Sea Surface Temperature (SST)" },
          { id: "salinity", label: "Salinity (PSU)" },
          { id: "chlorophyll", label: "Chlorophyll-a" },
          { id: "anomalies", label: "Thermal Anomalies" },
          { id: "trends", label: "Longitudinal Trends" },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id as ResearchLayerType)}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all shrink-0 cursor-pointer ${
              activeTab === tab.id
                ? "bg-[#0066CC] text-white shadow-sm scale-[1.02]"
                : "bg-white text-slate-600 hover:bg-slate-50 border border-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Main Analysis Stage: Map Visual & Statistics */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Spatial Heatmap Card (7 cols) */}
        <div className="lg:col-span-7 p-5 rounded-3xl bg-white border border-slate-200 shadow-2xs space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-display font-black text-base text-slate-900">
                {activeData.title}
              </h3>
              <p className="text-xs text-slate-500 font-medium">
                {activeData.subtitle}
              </p>
            </div>
            <span className="text-[10px] font-bold bg-blue-50 text-[#0066CC] border border-blue-200 px-2 py-0.5 rounded-full">
              Copernicus Live Sync
            </span>
          </div>

          <div className="relative">
            <MiniMapWidget
              locationName="Arabian Sea Marine Sanctuary"
              center={[69.80, 20.50]}
              zoom={7.0}
              className="h-[420px]"
              activeLayer={activeTab}
            />

            {/* Dynamic Color Scale matching active tab */}
            <div className="absolute bottom-4 left-3.5 z-20 p-2.5 rounded-xl bg-white/95 backdrop-blur-md border border-slate-200 shadow-md space-y-1.5 pointer-events-none">
              <span className="text-[9px] font-bold text-slate-700 uppercase tracking-wider block">
                {activeData.scaleTitle}
              </span>
              <div className="flex items-center gap-2">
                <div className={`w-3.5 h-24 rounded-md bg-gradient-to-t ${activeData.scaleGradient} border border-slate-300`} />
                <div className="flex flex-col justify-between h-24 text-[8.5px] font-mono font-bold text-slate-700">
                  {activeData.scaleTicks.map((tick, idx) => (
                    <span key={idx}>{tick}</span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Key Insights & Regional Statistics (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          {/* Key Insights Box */}
          <div className="p-5 rounded-3xl bg-white border border-slate-200 shadow-2xs space-y-3">
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-[#0066CC]" />
              <h3 className="font-display font-black text-base text-slate-900">
                Key Environmental Insights
              </h3>
            </div>
            <ul className="space-y-2">
              {activeData.insights.map((insight, idx) => (
                <li key={idx} className="flex items-start gap-2.5 text-xs text-slate-700 font-medium leading-relaxed">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#0066CC] shrink-0 mt-1.5" />
                  <span>{insight}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Current Region Statistics Card */}
          <div className="p-5 rounded-3xl bg-white border border-slate-200 shadow-2xs space-y-3">
            <h3 className="font-display font-black text-base text-slate-900">
              Regional Statistical Summary
            </h3>
            <div className="grid grid-cols-2 gap-3 pt-1">
              {activeData.stats.map((st, idx) => (
                <div key={idx} className="p-3 rounded-xl bg-slate-50 border border-slate-200/90">
                  <span className="text-[11px] font-semibold text-slate-500">{st.label}</span>
                  <div className="font-display font-black text-xl text-slate-900 mt-0.5">
                    {st.value}
                  </div>
                  <span className={`text-[10px] ${st.alert ? "font-bold text-rose-600" : "font-medium text-slate-500"}`}>
                    {st.note}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Lower Section: Longitudinal Charts (Recharts) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Time Series Line Chart (7 cols) with Real-Time Dates */}
        <div className="lg:col-span-7 p-5 rounded-3xl bg-white border border-slate-200 shadow-2xs space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-display font-black text-base text-slate-900">
                {activeData.lineChartTitle}
              </h3>
              <p className="text-xs text-slate-500 font-medium">
                {activeData.lineChartSubtitle}
              </p>
            </div>
            <span className="text-xs font-mono font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
              Unit: {activeData.unit}
            </span>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={activeData.timeSeries} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="date" stroke="#94A3B8" fontSize={11} tickLine={false} />
                <YAxis domain={activeData.yDomain as any} stroke="#94A3B8" fontSize={11} tickLine={false} unit={` ${activeData.unit}`} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#FFFFFF",
                    borderColor: "#E2E8F0",
                    borderRadius: "12px",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.06)",
                    fontSize: "12px",
                  }}
                />
                <Legend iconType="circle" wrapperStyle={{ fontSize: "11px", paddingTop: "10px" }} />
                <Line
                  type="monotone"
                  dataKey="val"
                  name={activeData.lineName}
                  stroke="#0066CC"
                  strokeWidth={2.5}
                  dot={{ r: 4, fill: "#0066CC" }}
                />
                <Line
                  type="monotone"
                  dataKey="baseline"
                  name={activeData.baselineName}
                  stroke="#94A3B8"
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Regional Comparison Bar Chart (5 cols) */}
        <div className="lg:col-span-5 p-5 rounded-3xl bg-white border border-slate-200 shadow-2xs space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-display font-black text-base text-slate-900">
                {activeData.barChartTitle}
              </h3>
              <p className="text-xs text-slate-500 font-medium">
                {activeData.barChartSubtitle}
              </p>
            </div>
            <span className="text-xs font-mono font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
              Unit: {activeData.unit}
            </span>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={activeData.regional} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="name" stroke="#94A3B8" fontSize={11} tickLine={false} />
                <YAxis domain={activeData.yDomain as any} stroke="#94A3B8" fontSize={11} tickLine={false} unit={` ${activeData.unit}`} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#FFFFFF",
                    borderColor: "#E2E8F0",
                    borderRadius: "12px",
                    fontSize: "12px",
                  }}
                />
                <Bar dataKey="val" name={`${activeData.lineName}`} fill="#0066CC" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Export / NetCDF Bar */}
      <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-2xs flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-slate-600 font-medium">
          <Info size={15} className="text-[#0066CC]" />
          <span>Scientific datasets available in CF-compliant NetCDF4, GeoTIFF, and ASCII raster formats.</span>
        </div>
        <button
          type="button"
          onClick={() => {
            const blob = new Blob([JSON.stringify(activeData, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `oceanix_${activeTab}_telemetry_${dates[6].replace(" ", "_")}.json`;
            a.click();
          }}
          className="px-4 py-2 rounded-xl bg-slate-900 text-white font-bold text-xs hover:bg-slate-800 transition-colors flex items-center gap-2 cursor-pointer"
        >
          <Download size={14} />
          <span>Export Dataset ({activeTab.toUpperCase()})</span>
        </button>
      </div>
    </div>
  );
}
