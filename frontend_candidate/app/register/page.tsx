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
  User as UserIcon,
  Building,
  ArrowRight,
  Anchor,
  ShieldAlert,
  Microscope,
  Compass,
} from "lucide-react";

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useUserMode();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organization, setOrganization] = useState("");
  const [role, setRole] = useState<UserMode>("fisherman");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !email || !password) {
      setError("Please fill in all required fields.");
      return;
    }
    setError("");
    setLoading(true);

    try {
      await register(name, email, password, role, organization);
      router.push("/dashboard");
    } catch {
      setError("Registration failed. Please try again.");
      setLoading(false);
    }
  };

  const roles: { id: UserMode; label: string; icon: typeof Anchor; desc: string }[] = [
    { id: "fisherman", label: "Fisherman", icon: Anchor, desc: "Safety alerts & sea states" },
    { id: "authority", label: "Port Authority", icon: ShieldAlert, desc: "Surveillance & compliance" },
    { id: "researcher", label: "Marine Researcher", icon: Microscope, desc: "Satellite & ocean anomalies" },
    { id: "operator", label: "Fleet Operator", icon: Compass, desc: "Route optimization" },
  ];

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center p-4 relative overflow-hidden py-10">
      <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-cyan/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 left-1/4 w-96 h-96 bg-go/10 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-lg bg-surface border border-border rounded-3xl p-6 sm:p-8 shadow-2xl relative z-10 backdrop-blur-xl">
        <div className="text-center mb-6">
          <div className="w-12 h-12 rounded-2xl bg-cyan/10 border border-cyan/30 flex items-center justify-center mx-auto mb-3 text-cyan shadow-lg shadow-cyan/10">
            <Waves size={26} />
          </div>
          <h1 className="font-display font-black text-2xl text-text-primary tracking-tight">
            Create ORCA Account
          </h1>
          <p className="text-xs sm:text-sm text-text-muted mt-1">
            Join the autonomous marine decision support network
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-xl bg-avoid/10 border border-avoid/40 text-avoid text-xs">
            {error}
          </div>
        )}

        <form onSubmit={handleRegister} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1.5 uppercase tracking-wider">
              Full Name *
            </label>
            <div className="relative">
              <UserIcon className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Captain John Doe"
                className="w-full bg-surface-light border border-border rounded-xl py-2.5 pl-10 pr-3 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-cyan transition-colors"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1.5 uppercase tracking-wider">
              Email Address *
            </label>
            <div className="relative">
              <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="john@maritime-guild.org"
                className="w-full bg-surface-light border border-border rounded-xl py-2.5 pl-10 pr-3 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-cyan transition-colors"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1.5 uppercase tracking-wider">
              Password *
            </label>
            <div className="relative">
              <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Create a strong password"
                className="w-full bg-surface-light border border-border rounded-xl py-2.5 pl-10 pr-3 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-cyan transition-colors"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-muted mb-1.5 uppercase tracking-wider">
              Organization / Vessel Name
            </label>
            <div className="relative">
              <Building className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
              <input
                type="text"
                value={organization}
                onChange={(e) => setOrganization(e.target.value)}
                placeholder="e.g. Coastal Fleet Alpha, JNPT, or University"
                className="w-full bg-surface-light border border-border rounded-xl py-2.5 pl-10 pr-3 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-cyan transition-colors"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-muted mb-2 uppercase tracking-wider">
              Select Your Role / Persona
            </label>
            <div className="grid grid-cols-2 gap-2">
              {roles.map((r) => {
                const Icon = r.icon;
                const isSelected = role === r.id;
                return (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => setRole(r.id)}
                    className={`p-2.5 rounded-xl border text-left transition-all ${
                      isSelected
                        ? "bg-cyan/15 border-cyan text-cyan shadow-sm"
                        : "bg-surface-light border-border text-text-muted hover:text-text-primary hover:bg-surface-light/80"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <Icon size={16} className={isSelected ? "text-cyan" : "text-text-muted"} />
                      <span className="font-bold text-xs text-text-primary">{r.label}</span>
                    </div>
                    <p className="text-[10px] text-text-muted leading-tight">{r.desc}</p>
                  </button>
                );
              })}
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl bg-cyan hover:bg-cyan/90 text-bg font-bold text-sm transition-all flex items-center justify-center gap-2 shadow-lg shadow-cyan/20 disabled:opacity-60 mt-2"
          >
            <span>{loading ? "Creating Account..." : "Create Account & Launch"}</span>
            <ArrowRight size={16} />
          </button>
        </form>

        <div className="text-center mt-6 text-xs text-text-muted">
          Already have an account?{" "}
          <Link href="/login" className="text-cyan font-bold hover:underline">
            Log In
          </Link>
        </div>
      </div>
    </div>
  );
}