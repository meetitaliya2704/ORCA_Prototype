import Link from "next/link";
import {
  Bot,
  ShieldCheck,
  Radio,
  MessageSquareText,
  Bell,
  Database,
  Map as MapIcon,
  ArrowRight,
  Sparkles,
} from "lucide-react";

export default function CapabilitiesPage() {
  const coreCapabilities = [
    {
      icon: Bot,
      color: "text-cyan bg-cyan/10 border-cyan/30",
      title: "Multi-Agent Arbitration",
      desc: "Five autonomous agents synthesize weather radar, buoy telemetry, ocean currents, and GIS boundaries in parallel with sub-second latency.",
    },
    {
      icon: ShieldCheck,
      color: "text-go bg-go/10 border-go/30",
      title: "Transparent Evidence",
      desc: "Every GO / WAIT / AVOID recommendation is accompanied by verifiable provenance, confidence ratings, and direct sensor timestamps.",
    },
    {
      icon: Radio,
      color: "text-wait bg-wait/10 border-wait/30",
      title: "Geospatial Nautical Radar",
      desc: "Interactive bathymetry, live AIS vessel traffic, squall propagation vectors, and safe navigational channels rendered on vector charts.",
    },
  ];

  const platformModules = [
    {
      icon: MessageSquareText,
      title: "AI Chat Co-Pilot",
      desc: "Ask natural-language questions and get instant, evidence-backed maritime safety answers tailored to your role.",
    },
    {
      icon: MapIcon,
      title: "Live Situational Map",
      desc: "Track vessel positions, storm fronts, and safe corridors on an interactive nautical chart updated in real time.",
    },
    {
      icon: Bell,
      title: "Smart Alerts",
      desc: "Proactive squall, swell, and compliance alerts pushed the moment risk conditions change near you.",
    },
    {
      icon: Database,
      title: "Unified Data Layer",
      desc: "A single, queryable source for buoy telemetry, satellite feeds, and historical ocean analytics.",
    },
  ];

  return (
    <div className="py-12 px-4 sm:px-6 lg:px-8 max-w-6xl mx-auto space-y-16">
      <div className="text-center max-w-3xl mx-auto space-y-4">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-cyan/10 border border-cyan/30 text-cyan text-xs font-semibold uppercase tracking-wider">
          <Sparkles size={14} />
          <span>Platform Capabilities</span>
        </div>
        <h1 className="font-display font-black text-3xl sm:text-5xl text-text-primary tracking-tight">
          Everything You Need to <span className="text-cyan">See Beyond the Surface</span>
        </h1>
        <p className="text-text-muted text-sm sm:text-base leading-relaxed">
          Oceanix pairs a collaborative network of autonomous AI agents with live oceanographic data to
          deliver instant, verifiable maritime decisions for every coastal stakeholder.
        </p>
      </div>

      <div className="space-y-6">
        <div className="text-center max-w-2xl mx-auto">
          <h2 className="font-display font-bold text-2xl sm:text-3xl text-text-primary">
            Engineered for High-Risk Marine Operations
          </h2>
          <p className="text-text-muted text-xs sm:text-sm mt-1">
            Core intelligence that powers every recommendation on the platform
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {coreCapabilities.map((c) => {
            const Icon = c.icon;
            return (
              <div
                key={c.title}
                className="p-6 rounded-3xl bg-surface border border-border space-y-3 hover:border-cyan/40 transition-colors shadow-sm"
              >
                <div className={`w-10 h-10 rounded-xl border flex items-center justify-center ${c.color}`}>
                  <Icon size={20} />
                </div>
                <h3 className="font-display font-bold text-lg text-text-primary">{c.title}</h3>
                <p className="text-text-muted text-xs sm:text-sm leading-relaxed">{c.desc}</p>
              </div>
            );
          })}
        </div>
      </div>

      <div className="space-y-6">
        <div className="text-center max-w-2xl mx-auto">
          <h2 className="font-display font-bold text-2xl sm:text-3xl text-text-primary">
            Inside the Live Platform
          </h2>
          <p className="text-text-muted text-xs sm:text-sm mt-1">
            Once you sign in, these modules keep you ahead of changing sea conditions
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {platformModules.map((m) => {
            const Icon = m.icon;
            return (
              <div
                key={m.title}
                className="p-5 rounded-2xl bg-surface border border-border space-y-2.5 hover:border-cyan/50 transition-all shadow-sm"
              >
                <div className="w-9 h-9 rounded-xl bg-cyan/10 border border-cyan/30 flex items-center justify-center text-cyan">
                  <Icon size={18} />
                </div>
                <h4 className="font-display font-bold text-base text-text-primary">{m.title}</h4>
                <p className="text-xs text-text-muted leading-relaxed">{m.desc}</p>
              </div>
            );
          })}
        </div>
      </div>

      <div className="p-8 sm:p-10 rounded-3xl bg-gradient-to-r from-surface via-surface-light to-surface border border-cyan/30 text-center space-y-4">
        <h3 className="font-display font-black text-2xl sm:text-3xl text-text-primary">
          Ready to See It in Action?
        </h3>
        <p className="text-text-muted text-sm max-w-xl mx-auto">
          Sign in to your Situation Deck or create a free account to explore every capability across
          Fisherman, Port Authority, Researcher, and Fleet Operator modes.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
          <Link
            href="/login"
            className="px-6 py-3 rounded-xl bg-cyan text-bg font-bold text-sm hover:bg-cyan/90 transition-all flex items-center gap-2 shadow-lg shadow-cyan/20"
          >
            <span>Login to Situation Deck</span>
            <ArrowRight size={16} />
          </Link>
          <Link
            href="/register"
            className="px-6 py-3 rounded-xl bg-surface-light hover:bg-surface border border-border text-sm font-semibold text-text-primary transition-colors"
          >
            Create Free Account
          </Link>
        </div>
      </div>
    </div>
  );
}
