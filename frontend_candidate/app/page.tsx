"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import {
  Play,
  ArrowRight,
  ShieldCheck,
  BrainCircuit,
  Waves,
  Users,
  Anchor,
  Shield,
  Microscope,
  Compass,
} from "lucide-react";
import { useUserMode } from "@/lib/context";
import type { UserMode } from "@/lib/types";

export default function HomePage() {
  const router = useRouter();
  const { switchRole } = useUserMode();

  const handleRoleLaunch = (role: UserMode) => {
    switchRole(role);
    router.push("/dashboard");
  };

  const featurePills = [
    {
      title: "Better Safety",
      description: "Detect hazards, get early warnings and make safer decisions at sea.",
      icon: ShieldCheck,
      color: "text-blue-600 bg-blue-50 border-blue-200",
    },
    {
      title: "Smarter Decisions",
      description: "Use real-time data and AI insights for optimal routes and operations.",
      icon: BrainCircuit,
      color: "text-indigo-600 bg-indigo-50 border-indigo-200",
    },
    {
      title: "Healthier Oceans",
      description: "Monitor marine health and support sustainable practices.",
      icon: Waves,
      color: "text-teal-600 bg-teal-50 border-teal-200",
    },
    {
      title: "Stronger Communities",
      description: "Protect livelihoods and build a resilient coastal future.",
      icon: Users,
      color: "text-cyan-600 bg-cyan-50 border-cyan-200",
    },
  ];

  const stakeholders = [
    {
      role: "fisherman" as UserMode,
      title: "Fisherman",
      description: "Get safe fishing advice, weather alerts and optimal routes for a better tomorrow.",
      icon: Anchor,
      tag: "Coastal Safety",
    },
    {
      role: "authority" as UserMode,
      title: "Port Authority",
      description: "Improve port operations, manage risks and ensure safer coastal infrastructure.",
      icon: Shield,
      tag: "Maritime Traffic",
    },
    {
      role: "researcher" as UserMode,
      title: "Researcher",
      description: "Access multi-source data, advanced analytics and research-grade insights.",
      icon: Microscope,
      tag: "Ocean Analytics",
    },
    {
      role: "operator" as UserMode,
      title: "Fleet Operator",
      description: "Optimize routes, monitor vessels and reduce operational risks with real-time intelligence.",
      icon: Compass,
      tag: "Route Planning",
    },
  ];

  return (
    <div className="bg-[#F8FAFC] min-h-screen">
      {/* 1. Immersive Hero Section with Cycling Background Images */}
      <section className="relative min-h-[82vh] flex items-center overflow-hidden border-b border-slate-200/80">
        {/* Animated Background Slides */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="hero-slide" />
          <div className="hero-slide" />
          <div className="hero-slide" />
          <div className="hero-slide" />
          <div className="absolute inset-0 bg-gradient-to-r from-slate-950/90 via-slate-950/70 to-slate-950/40" />
        </div>

        <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 w-full">
          <div className="max-w-3xl space-y-6 text-left">
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-blue-500/20 border border-blue-400/40 text-blue-200 text-xs font-bold backdrop-blur-md shadow-xs">
              <span>Next-Gen Marine Decision Support</span>
            </div>

            <h1 className="font-display font-black text-4xl sm:text-6xl lg:text-7xl text-white tracking-tight leading-[1.08] drop-shadow-md">
              See Beyond the Surface.
            </h1>

            <p className="text-base sm:text-xl text-slate-200 font-medium leading-relaxed max-w-2xl drop-shadow">
              AI-powered marine intelligence for safer seas, smarter decisions. Powered by official INCOIS, IMD, and Copernicus telemetry.
            </p>

            {/* Action Buttons */}
            <div className="flex flex-wrap items-center gap-4 pt-3">
              <Link
                href="/select-role"
                className="px-8 py-4 rounded-2xl bg-[#0066CC] hover:bg-[#0052A3] text-white font-extrabold text-sm sm:text-base tracking-wide flex items-center gap-2.5 shadow-lg shadow-blue-600/35 transition-all hover:scale-[1.02] active:scale-[0.98]"
              >
                <Play size={18} fill="currentColor" />
                <span>Try Demo</span>
              </Link>

              <Link
                href="/login"
                className="px-8 py-4 rounded-2xl bg-white hover:bg-slate-100 text-slate-900 font-bold text-sm sm:text-base shadow-lg transition-all hover:scale-[1.02]"
              >
                Login
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* 4 Benefit Pills Strip */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 -mt-8 relative z-20">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {featurePills.map((pill) => {
            const Icon = pill.icon;
            return (
              <div
                key={pill.title}
                className="p-5 rounded-2xl bg-white/95 backdrop-blur-md border border-slate-200 shadow-md hover:border-[#0066CC]/50 transition-all space-y-2 text-left"
              >
                <div className={`w-9 h-9 rounded-xl flex items-center justify-center border ${pill.color}`}>
                  <Icon size={18} />
                </div>
                <h3 className="font-display font-black text-sm text-slate-900">
                  {pill.title}
                </h3>
                <p className="text-xs text-slate-500 font-medium leading-relaxed">
                  {pill.description}
                </p>
              </div>
            );
          })}
        </div>
      </section>

      {/* 2. Stakeholder Solutions Section (Page 1) */}
      <section className="py-20 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-12">
        <div className="text-center space-y-3 max-w-2xl mx-auto">
          <span className="text-xs font-black tracking-widest text-[#0066CC] uppercase">
            Built for Every Stakeholder
          </span>
          <h2 className="font-display font-black text-3xl sm:text-4xl text-slate-900 tracking-tight">
            Solutions for a Safer, Smarter Ocean
          </h2>
          <p className="text-sm font-medium text-slate-500 leading-relaxed">
            Oceanix serves multiple stakeholders with tailored insights, tools and real-time intelligence.
          </p>
        </div>

        {/* 4 Persona Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {stakeholders.map((s) => {
            const Icon = s.icon;
            return (
              <button
                key={s.role}
                type="button"
                onClick={() => handleRoleLaunch(s.role)}
                className="group p-6 rounded-3xl bg-white border border-slate-200 hover:border-[#0066CC] shadow-2xs hover:shadow-xl transition-all text-left flex flex-col justify-between space-y-6"
              >
                <div className="space-y-4">
                  <div className="w-12 h-12 rounded-2xl bg-blue-50 text-[#0066CC] flex items-center justify-center group-hover:scale-110 transition-transform">
                    <Icon size={24} />
                  </div>
                  <div>
                    <h3 className="font-display font-black text-lg text-slate-900 group-hover:text-[#0066CC] transition-colors">
                      {s.title}
                    </h3>
                    <p className="text-xs text-slate-500 font-medium mt-1 leading-relaxed">
                      {s.description}
                    </p>
                  </div>
                </div>

                <div className="pt-4 border-t border-slate-100 flex items-center justify-between text-xs font-bold text-[#0066CC]">
                  <span>Enter Deck</span>
                  <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
                </div>
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
