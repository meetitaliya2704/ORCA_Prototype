"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import {
  Play,
  User,
  Plus,
  Zap,
  Anchor,
  Shield,
  Microscope,
  Compass,
  ArrowRight,
  Sparkles,
} from "lucide-react";
import { useUserMode, DEFAULT_PERSONAS } from "@/lib/context";
import type { UserMode } from "@/lib/types";

export default function GetStartedPage() {
  const router = useRouter();
  const { login, switchRole } = useUserMode();
  const [showLoginForm, setShowLoginForm] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleTryDemo = () => {
    switchRole("fisherman");
    router.push("/dashboard");
  };

  const handleQuickRoleAccess = (role: UserMode) => {
    switchRole(role);
    router.push("/dashboard");
  };

  const handleFormLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
    await login(email, password || "pass", "fisherman");
    router.push("/dashboard");
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-[#F8FAFC] py-12 px-4 sm:px-6 lg:px-8 flex flex-col items-center justify-center">
      {/* Central Get Started Box */}
      <div className="w-full max-w-xl text-center space-y-6">
        {/* Brand Icon */}
        <div className="w-16 h-16 rounded-2xl bg-blue-50 border border-blue-200/80 mx-auto flex items-center justify-center shadow-xs">
          <Image
            src="/brand/oceanix-logo.png"
            alt="Oceanix"
            width={44}
            height={44}
            className="w-10 h-10 object-contain"
          />
        </div>

        <div className="space-y-2">
          <h1 className="font-display font-black text-3xl sm:text-4xl text-slate-900 tracking-tight">
            Get Started
          </h1>
          <p className="text-sm font-medium text-slate-500">
            Choose how you want to access Oceanix Marine Intelligence
          </p>
        </div>

        {/* Action Buttons */}
        <div className="space-y-3 pt-2">
          {/* Primary: Try Demo (No Signup Required) */}
          <button
            type="button"
            onClick={handleTryDemo}
            className="w-full py-4 px-6 rounded-2xl bg-[#0066CC] hover:bg-[#0052A3] text-white font-extrabold text-base tracking-wide flex items-center justify-center gap-2.5 shadow-lg shadow-blue-600/20 transition-all hover:scale-[1.01] active:scale-[0.99]"
          >
            <Play size={18} fill="currentColor" />
            <span>Try Demo (No Signup Required)</span>
          </button>

          <div className="relative py-2 flex items-center justify-center">
            <span className="w-full border-t border-slate-200" />
            <span className="absolute px-3 bg-[#F8FAFC] text-xs font-semibold text-slate-400 uppercase">
              Or
            </span>
          </div>

          {!showLoginForm ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setShowLoginForm(true)}
                className="py-3 px-4 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 font-bold text-xs flex items-center justify-center gap-2 transition-all shadow-2xs"
              >
                <User size={15} className="text-[#0066CC]" />
                <span>Login to your account</span>
              </button>

              <Link
                href="/register"
                className="py-3 px-4 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 font-bold text-xs flex items-center justify-center gap-2 transition-all shadow-2xs"
              >
                <Plus size={15} className="text-slate-500" />
                <span>Create a new account</span>
              </Link>
            </div>
          ) : (
            <form onSubmit={handleFormLogin} className="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm space-y-3 text-left">
              <div className="space-y-1">
                <label className="text-[11px] font-bold text-slate-600">Email or Username</label>
                <input
                  type="text"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="user@marine.gov.in"
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0066CC]"
                />
              </div>
              <div className="space-y-1">
                <label className="text-[11px] font-bold text-slate-600">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0066CC]"
                />
              </div>
              <button
                type="submit"
                className="w-full py-2.5 rounded-xl bg-slate-900 text-white font-bold text-xs hover:bg-slate-800 transition-colors"
              >
                Sign In
              </button>
            </form>
          )}
        </div>
      </div>

      {/* Direct Stakeholder Access Strip */}
      <div className="w-full max-w-5xl mt-14 space-y-4">
        <div className="flex items-center gap-2 text-slate-800 font-display font-black text-lg">
          <Zap size={18} className="text-[#0066CC] fill-[#0066CC]" />
          <span>Direct Stakeholder Access</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Fisherman Access */}
          <button
            type="button"
            onClick={() => handleQuickRoleAccess("fisherman")}
            className="group p-5 rounded-2xl bg-white border border-slate-200 hover:border-[#0066CC] shadow-2xs hover:shadow-md transition-all text-left space-y-3"
          >
            <div className="w-10 h-10 rounded-xl bg-blue-50 text-[#0066CC] flex items-center justify-center group-hover:scale-105 transition-transform">
              <Anchor size={20} />
            </div>
            <div>
              <h3 className="font-display font-black text-sm text-slate-900 group-hover:text-[#0066CC] transition-colors">
                Fisherman Access
              </h3>
              <p className="text-xs text-slate-500 font-medium mt-1 leading-relaxed">
                See how Oceanix helps fishermen get safe and accurate fishing zone advice.
              </p>
            </div>
            <div className="pt-2 flex items-center gap-1.5 text-xs font-bold text-[#0066CC]">
              <span>Enter Deck</span>
              <ArrowRight size={13} className="group-hover:translate-x-1 transition-transform" />
            </div>
          </button>

          {/* Authority Access */}
          <button
            type="button"
            onClick={() => handleQuickRoleAccess("authority")}
            className="group p-5 rounded-2xl bg-white border border-slate-200 hover:border-[#0066CC] shadow-2xs hover:shadow-md transition-all text-left space-y-3"
          >
            <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center group-hover:scale-105 transition-transform">
              <Shield size={20} />
            </div>
            <div>
              <h3 className="font-display font-black text-sm text-slate-900 group-hover:text-[#0066CC] transition-colors">
                Port Authority Access
              </h3>
              <p className="text-xs text-slate-500 font-medium mt-1 leading-relaxed">
                Explore how authorities monitor, analyze and respond to marine hazards.
              </p>
            </div>
            <div className="pt-2 flex items-center gap-1.5 text-xs font-bold text-[#0066CC]">
              <span>Enter Deck</span>
              <ArrowRight size={13} className="group-hover:translate-x-1 transition-transform" />
            </div>
          </button>

          {/* Researcher Access */}
          <button
            type="button"
            onClick={() => handleQuickRoleAccess("researcher")}
            className="group p-5 rounded-2xl bg-white border border-slate-200 hover:border-[#0066CC] shadow-2xs hover:shadow-md transition-all text-left space-y-3"
          >
            <div className="w-10 h-10 rounded-xl bg-teal-50 text-teal-600 flex items-center justify-center group-hover:scale-105 transition-transform">
              <Microscope size={20} />
            </div>
            <div>
              <h3 className="font-display font-black text-sm text-slate-900 group-hover:text-[#0066CC] transition-colors">
                Researcher Access
              </h3>
              <p className="text-xs text-slate-500 font-medium mt-1 leading-relaxed">
                Access marine data, insights and analysis tools for research and study.
              </p>
            </div>
            <div className="pt-2 flex items-center gap-1.5 text-xs font-bold text-[#0066CC]">
              <span>Enter Deck</span>
              <ArrowRight size={13} className="group-hover:translate-x-1 transition-transform" />
            </div>
          </button>

          {/* Fleet Access */}
          <button
            type="button"
            onClick={() => handleQuickRoleAccess("operator")}
            className="group p-5 rounded-2xl bg-white border border-slate-200 hover:border-[#0066CC] shadow-2xs hover:shadow-md transition-all text-left space-y-3"
          >
            <div className="w-10 h-10 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center group-hover:scale-105 transition-transform">
              <Compass size={20} />
            </div>
            <div>
              <h3 className="font-display font-black text-sm text-slate-900 group-hover:text-[#0066CC] transition-colors">
                Fleet Operator Access
              </h3>
              <p className="text-xs text-slate-500 font-medium mt-1 leading-relaxed">
                See how fleet operators get operational and route safety insights.
              </p>
            </div>
            <div className="pt-2 flex items-center gap-1.5 text-xs font-bold text-[#0066CC]">
              <span>Enter Deck</span>
              <ArrowRight size={13} className="group-hover:translate-x-1 transition-transform" />
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}