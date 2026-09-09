"use client";

import Link from "next/link";
import {
  ArrowRight,
  ShieldCheck,
  Bot,
  Compass,
  Radio,
  Anchor,
  ShieldAlert,
  Microscope,
} from "lucide-react";
import { useUserMode } from "@/lib/context";

export default function HomePage() {
  const { isLoggedIn, user } = useUserMode();

  const personas = [
    {
      title: "Coastal Fishermen",
      role: "Live wave heights, squall warnings & safe navigation",
      icon: Anchor,
      badge: "Fisherman Mode",
      color: "text-cyan bg-cyan/10 border-cyan/30",
    },
    {
      title: "Port & Coastal Authorities",
      role: "Vessel traffic surveillance, AIS tracking & storm alerts",
      icon: ShieldAlert,
      badge: "Authority Mode",
      color: "text-avoid bg-avoid/10 border-avoid/30",
    },
    {
      title: "Marine Researchers",
      role: "Sea surface temperature anomalies, salinity & coral monitoring",
      icon: Microscope,
      badge: "Researcher Mode",
      color: "text-go bg-go/10 border-go/30",
    },
    {
      title: "Commercial Fleet Operators",
      role: "Route risk mitigation, fuel optimization & collision avoidance",
      icon: Compass,
      badge: "Operator Mode",
      color: "text-wait bg-wait/10 border-wait/30",
    },
  ];

  return (
    <div className="overflow-hidden">
      <section className="relative min-h-[88vh] flex items-center">
        <div className="absolute inset-0 overflow-hidden">
          <div className="hero-slide" />
          <div className="hero-slide" />
          <div className="hero-slide" />
          <div className="hero-slide" />
          <div className="absolute inset-0 bg-gradient-to-r from-black/55 via-black/25 to-transparent" />
        </div>

        <div className="relative z-10 px-4 sm:px-8 lg:px-16 max-w-5xl py-20 space-y-8">
          <h1 className="font-display font-black text-4xl sm:text-6xl lg:text-7xl tracking-tight leading-[1.08] text-white drop-shadow-lg">
            The Future of Marine Intelligence Starts Here{" "}
            <span className="text-[#E11D2E]">See Beyond the Surface</span>
          </h1>
          <div className="flex items-center gap-3">
            <span className="h-px w-10 bg-[#E11D2E]" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#E11D2E]" />
          </div>

          <div className="flex flex-col sm:flex-row items-start gap-4 pt-2">
            {isLoggedIn ? (
              <Link
                href="/dashboard"
                className="w-full sm:w-auto px-8 py-3.5 rounded-2xl bg-white text-text-primary font-bold text-sm sm:text-base hover:bg-cyan hover:text-white transition-all flex items-center justify-center gap-2.5 shadow-xl"
              >
                <span>Enter Situation Deck ({user?.name})</span>
                <ArrowRight size={18} />
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  className="w-full sm:w-auto px-8 py-3.5 rounded-2xl bg-white text-text-primary font-bold text-sm sm:text-base hover:bg-cyan hover:text-white transition-all flex items-center justify-center gap-2.5 shadow-xl"
                >
                  <span>Login to Situation Deck</span>
                  <ArrowRight size={18} />
                </Link>
                <Link
                  href="/register"
                  className="w-full sm:w-auto px-8 py-3.5 rounded-2xl bg-white/15 hover:bg-white/25 border border-white/70 text-sm sm:text-base font-semibold text-white transition-all flex items-center justify-center gap-2"
                >
                  <span>Create Free Account</span>
                </Link>
              </>
            )}
          </div>
        </div>
      </section>

      <section id="features" className="px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto space-y-12 py-20">
        <div className="text-center max-w-2xl mx-auto space-y-2">
          <h2 className="font-display font-bold text-2xl sm:text-4xl text-text-primary">
            Engineered for High-Risk Marine Operations
          </h2>
          <p className="text-text-muted text-xs sm:text-sm">
            Everything you need to assess coastal hazards, optimize routes, and comply with maritime safety standards.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-6 rounded-3xl bg-surface border border-border space-y-3 hover:border-cyan/40 transition-colors shadow-sm">
            <div className="w-10 h-10 rounded-xl bg-cyan/10 border border-cyan/30 flex items-center justify-center text-cyan">
              <Bot size={20} />
            </div>
            <h3 className="font-display font-bold text-lg text-text-primary">Multi-Agent Arbitration</h3>
            <p className="text-text-muted text-xs sm:text-sm leading-relaxed">
              Five autonomous agents synthesize weather radar, buoy telemetry, ocean currents, and GIS boundaries in parallel with sub-second latency.
            </p>
          </div>

          <div className="p-6 rounded-3xl bg-surface border border-border space-y-3 hover:border-cyan/40 transition-colors shadow-sm">
            <div className="w-10 h-10 rounded-xl bg-go/10 border border-go/30 flex items-center justify-center text-go">
              <ShieldCheck size={20} />
            </div>
            <h3 className="font-display font-bold text-lg text-text-primary">Transparent Evidence</h3>
            <p className="text-text-muted text-xs sm:text-sm leading-relaxed">
              Every GO / WAIT / AVOID recommendation is accompanied by verifiable provenance, confidence ratings, and direct sensor timestamps.
            </p>
          </div>

          <div className="p-6 rounded-3xl bg-surface border border-border space-y-3 hover:border-cyan/40 transition-colors shadow-sm">
            <div className="w-10 h-10 rounded-xl bg-wait/10 border border-wait/30 flex items-center justify-center text-wait">
              <Radio size={20} />
            </div>
            <h3 className="font-display font-bold text-lg text-text-primary">Geospatial Nautical Radar</h3>
            <p className="text-text-muted text-xs sm:text-sm leading-relaxed">
              Interactive bathymetry, live AIS vessel traffic, squall propagation vectors, and safe navigational channels rendered on vector charts.
            </p>
          </div>
        </div>
      </section>

      <section className="px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto space-y-8 pb-20">
        <div className="text-center max-w-2xl mx-auto space-y-2">
          <h2 className="font-display font-bold text-2xl sm:text-4xl text-text-primary">
            Tailored for Every Maritime Stakeholder
          </h2>
          <p className="text-text-muted text-xs sm:text-sm">
            Switch effortlessly between personas with adaptive layers, alerts, and AI prompts
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {personas.map((p) => {
            const Icon = p.icon;
            return (
              <div
                key={p.title}
                className="p-5 rounded-2xl bg-surface border border-border space-y-3 flex flex-col justify-between hover:border-cyan/50 transition-all shadow-sm"
              >
                <div>
                  <div className={`w-9 h-9 rounded-xl border flex items-center justify-center mb-3 ${p.color}`}>
                    <Icon size={18} />
                  </div>
                  <h4 className="font-display font-bold text-base text-text-primary">{p.title}</h4>
                  <p className="text-xs text-text-muted mt-1 leading-relaxed">{p.role}</p>
                </div>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border self-start ${p.color}`}>
                  {p.badge}
                </span>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
