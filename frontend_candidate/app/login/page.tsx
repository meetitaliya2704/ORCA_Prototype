"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useUserMode } from "@/lib/context";
import { UserMode } from "@/lib/types";
import {
  Waves,
  Lock,
  Mail,
  ArrowRight,
  Eye,
  EyeOff,
  Anchor,
  ShieldAlert,
  Microscope,
  Compass,
  Sparkles,
} from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useUserMode();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError("Please enter your username/email and password.");
      return;
    }
    setError("");
    setLoading(true);

    try {
      await login(email, password, "fisherman");
      router.push("/dashboard");
    } catch {
      setError("Login failed. Please check your credentials.");
      setLoading(false);
    }
  };

  const handleQuickDemo = async (role: UserMode, demoName: string, demoEmail: string) => {
    setLoading(true);
    await login(demoEmail, "demo123", role, demoName);
    router.push("/dashboard");
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center p-4 relative overflow-hidden">
      {/* Glow accents */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-cyan/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-go/10 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-md bg-surface border border-border rounded-3xl p-6 sm:p-8 shadow-2xl relative z-10 backdrop-blur-xl">
        <div className="text-center mb-6">
          <div className="w-12 h-12 rounded-2xl bg-cyan/10 border border-cyan/30 flex items-center justify-center mx-auto mb-3 text-cyan shadow-lg shadow-cyan/10">
            <Waves size={26} />
          </div>
          <h1 className="font-display font-black text-2xl text-text-primary tracking-tight">
            Welcome to ORCA
          </h1>
          <p className="text-xs sm:text-sm text-text-muted mt-1">
            Sign in to access your marine intelligence situation deck
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-xl bg-avoid/10 border border-avoid/40 text-avoid text-xs">
            {error}
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1.5 uppercase tracking-wider">
              Username or Email
            </label>
            <div className="relative">
              <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
              <input
                type="text"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="captain@maritime.org"
                className="w-full bg-surface-light border border-border rounded-xl py-2.5 pl-10 pr-3 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-cyan transition-colors"
                required
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider">
                Password
              </label>
              <a href="#" className="text-[11px] text-cyan hover:underline">
                Forgot password?
              </a>
            </div>
            <div className="relative">
              <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-surface-light border border-border rounded-xl py-2.5 pl-10 pr-10 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-cyan transition-colors"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl bg-cyan hover:bg-cyan/90 text-bg font-bold text-sm transition-all flex items-center justify-center gap-2 shadow-lg shadow-cyan/20 disabled:opacity-60"
          >
            <span>{loading ? "Authenticating..." : "Sign In to Deck"}</span>
            <ArrowRight size={16} />
          </button>
        </form>

        {/* 1-Click Persona Demo Access */}
        <div className="mt-6 pt-5 border-t border-border/70">
          <div className="flex items-center justify-center gap-1.5 text-xs text-text-muted mb-3 font-semibold uppercase tracking-wider">
            <Sparkles size={13} className="text-cyan" />
            <span>Instant Demo Access</span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <button
              onClick={() => handleQuickDemo("fisherman", "Captain Ramesh", "ramesh@fisheries.org")}
              className="p-2 rounded-xl bg-surface-light hover:bg-cyan/10 border border-border hover:border-cyan/40 text-left transition-all flex items-center gap-2"
            >
              <Anchor size={14} className="text-cyan shrink-0" />
              <span className="truncate font-medium">Fisherman</span>
            </button>
            <button
              onClick={() => handleQuickDemo("authority", "Commander Rao", "rao@coastguard.gov")}
              className="p-2 rounded-xl bg-surface-light hover:bg-avoid/10 border border-border hover:border-avoid/40 text-left transition-all flex items-center gap-2"
            >
              <ShieldAlert size={14} className="text-avoid shrink-0" />
              <span className="truncate font-medium">Port Authority</span>
            </button>
            <button
              onClick={() => handleQuickDemo("researcher", "Dr. Ananya Sen", "ananya@oceanology.res")}
              className="p-2 rounded-xl bg-surface-light hover:bg-go/10 border border-border hover:border-go/40 text-left transition-all flex items-center gap-2"
            >
              <Microscope size={14} className="text-go shrink-0" />
              <span className="truncate font-medium">Researcher</span>
            </button>
            <button
              onClick={() => handleQuickDemo("operator", "Capt. Vikram Singhania", "vikram@maersk-line.com")}
              className="p-2 rounded-xl bg-surface-light hover:bg-wait/10 border border-border hover:border-wait/40 text-left transition-all flex items-center gap-2"
            >
              <Compass size={14} className="text-wait shrink-0" />
              <span className="truncate font-medium">Fleet Operator</span>
            </button>
          </div>
        </div>

        {/* Register Link */}
        <div className="text-center mt-6 text-xs text-text-muted">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="text-cyan font-bold hover:underline">
            Register for Free
          </Link>
        </div>
      </div>
    </div>
  );
}