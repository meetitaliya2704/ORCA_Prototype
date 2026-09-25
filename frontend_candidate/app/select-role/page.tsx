"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Anchor,
  Shield,
  Microscope,
  Compass,
  ArrowRight,
  ArrowLeft,
} from "lucide-react";
import { useUserMode } from "@/lib/context";
import type { UserMode } from "@/lib/types";

export default function SelectRolePage() {
  const router = useRouter();
  const { switchRole } = useUserMode();

  const handleSelect = (role: UserMode) => {
    switchRole(role);
    router.push("/dashboard");
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-[#F8FAFC] py-12 px-4 sm:px-6 lg:px-8 flex flex-col justify-center">
      <div className="max-w-5xl mx-auto w-full space-y-8">
        {/* Top Back Navigation */}
        <div className="flex items-center justify-between">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-xs font-bold text-slate-600 hover:text-[#0066CC] transition-colors"
          >
            <ArrowLeft size={16} />
            <span>Back</span>
          </Link>
          <span className="text-xs font-semibold text-slate-400">
            Personalized Operational Mode
          </span>
        </div>

        {/* Heading */}
        <div className="text-center space-y-2 max-w-2xl mx-auto">
          <h1 className="font-display font-black text-3xl sm:text-4xl text-slate-900 tracking-tight">
            What are you using ORCA for?
          </h1>
          <p className="text-sm font-medium text-slate-500">
            Select your role to get a personalized experience
          </p>
        </div>

        {/* 4 Large Role Selection Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-4">
          {/* 1. Fisherman */}
          <button
            type="button"
            onClick={() => handleSelect("fisherman")}
            className="group p-7 rounded-3xl bg-white border border-slate-200 hover:border-[#0066CC] shadow-2xs hover:shadow-xl transition-all text-left flex items-start gap-5 relative overflow-hidden"
          >
            <div className="w-14 h-14 rounded-2xl bg-blue-50 text-[#0066CC] flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform">
              <Anchor size={28} />
            </div>
            <div className="space-y-2 flex-1">
              <h3 className="font-display font-black text-xl text-slate-900 group-hover:text-[#0066CC] transition-colors">
                I'm a Fisherman
              </h3>
              <p className="text-xs text-slate-600 font-medium leading-relaxed">
                Get safe, reliable and real-time advice for your fishing trips with INCOIS PFZ maps and wave alerts.
              </p>
              <div className="pt-3 flex items-center gap-2 text-xs font-black text-[#0066CC]">
                <span className="px-3 py-1.5 rounded-xl bg-blue-50">Go Safely</span>
                <div className="w-6 h-6 rounded-full bg-[#0066CC] text-white flex items-center justify-center group-hover:translate-x-1 transition-transform">
                  <ArrowRight size={13} />
                </div>
              </div>
            </div>
          </button>

          {/* 2. Port Authority */}
          <button
            type="button"
            onClick={() => handleSelect("authority")}
            className="group p-7 rounded-3xl bg-white border border-slate-200 hover:border-[#0066CC] shadow-2xs hover:shadow-xl transition-all text-left flex items-start gap-5 relative overflow-hidden"
          >
            <div className="w-14 h-14 rounded-2xl bg-amber-50 text-amber-600 flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform">
              <Shield size={28} />
            </div>
            <div className="space-y-2 flex-1">
              <h3 className="font-display font-black text-xl text-slate-900 group-hover:text-[#0066CC] transition-colors">
                I'm a Port Authority
              </h3>
              <p className="text-xs text-slate-600 font-medium leading-relaxed">
                Monitor port activities, track vessels at risk, issue storm warnings, and respond to incidents faster.
              </p>
              <div className="pt-3 flex items-center gap-2 text-xs font-black text-[#0066CC]">
                <span className="px-3 py-1.5 rounded-xl bg-blue-50">Monitor & Respond</span>
                <div className="w-6 h-6 rounded-full bg-[#0066CC] text-white flex items-center justify-center group-hover:translate-x-1 transition-transform">
                  <ArrowRight size={13} />
                </div>
              </div>
            </div>
          </button>

          {/* 3. Researcher */}
          <button
            type="button"
            onClick={() => handleSelect("researcher")}
            className="group p-7 rounded-3xl bg-white border border-slate-200 hover:border-[#0066CC] shadow-2xs hover:shadow-xl transition-all text-left flex items-start gap-5 relative overflow-hidden"
          >
            <div className="w-14 h-14 rounded-2xl bg-teal-50 text-teal-600 flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform">
              <Microscope size={28} />
            </div>
            <div className="space-y-2 flex-1">
              <h3 className="font-display font-black text-xl text-slate-900 group-hover:text-[#0066CC] transition-colors">
                I'm a Researcher
              </h3>
              <p className="text-xs text-slate-600 font-medium leading-relaxed">
                Access ocean data, run thermal anomaly analysis, inspect chlorophyll concentration, and support scientific study.
              </p>
              <div className="pt-3 flex items-center gap-2 text-xs font-black text-[#0066CC]">
                <span className="px-3 py-1.5 rounded-xl bg-blue-50">Analyze Ocean</span>
                <div className="w-6 h-6 rounded-full bg-[#0066CC] text-white flex items-center justify-center group-hover:translate-x-1 transition-transform">
                  <ArrowRight size={13} />
                </div>
              </div>
            </div>
          </button>

          {/* 4. Fleet Operator */}
          <button
            type="button"
            onClick={() => handleSelect("operator")}
            className="group p-7 rounded-3xl bg-white border border-slate-200 hover:border-[#0066CC] shadow-2xs hover:shadow-xl transition-all text-left flex items-start gap-5 relative overflow-hidden"
          >
            <div className="w-14 h-14 rounded-2xl bg-purple-50 text-purple-600 flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform">
              <Compass size={28} />
            </div>
            <div className="space-y-2 flex-1">
              <h3 className="font-display font-black text-xl text-slate-900 group-hover:text-[#0066CC] transition-colors">
                I'm a Fleet Operator
              </h3>
              <p className="text-xs text-slate-600 font-medium leading-relaxed">
                Plan commercial routes, track vessel fleets, calculate voyage fuel savings, and optimize operations with real-time insights.
              </p>
              <div className="pt-3 flex items-center gap-2 text-xs font-black text-[#0066CC]">
                <span className="px-3 py-1.5 rounded-xl bg-blue-50">Optimize Route</span>
                <div className="w-6 h-6 rounded-full bg-[#0066CC] text-white flex items-center justify-center group-hover:translate-x-1 transition-transform">
                  <ArrowRight size={13} />
                </div>
              </div>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}

