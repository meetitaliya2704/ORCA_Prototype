"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { Sparkles, ArrowRight, Menu, X, Bell } from "lucide-react";
import { useUserMode } from "@/lib/context";
import { useState } from "react";

export default function PublicNavbar() {
  const pathname = usePathname();
  const { user, isLoggedIn, logout } = useUserMode();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navLinks = [
    { href: "/", label: "Home" },
    { href: "/dashboard", label: "Dashboard" },
    { href: "/map", label: "Nautical Map" },
    { href: "/alerts", label: "Advisories" },
    { href: "/capabilities", label: "Features" },
    { href: "/about", label: "About" },
  ];

  return (
    <header className="sticky top-0 z-50 bg-white/95 backdrop-blur-md border-b border-slate-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-[#0066CC]/10 border border-[#0066CC]/30 flex items-center justify-center overflow-hidden">
            <Image src="/brand/oceanix-logo.png" alt="Oceanix" width={36} height={36} className="w-full h-full object-cover scale-125" />
          </div>
          <span className="font-display font-black text-xl tracking-tight text-slate-900">
            Oceanix
          </span>
        </Link>

        {/* Top Navbar Links */}
        <nav className="hidden md:flex items-center gap-7 text-sm font-medium">
          {navLinks.map((link) => {
            const isActive =
              link.href === "/dashboard"
                ? pathname === "/dashboard" || pathname === "/why-orca"
                : pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`transition-colors hover:text-[#0066CC] ${
                  isActive ? "text-[#0066CC] font-bold border-b-2 border-[#0066CC] py-5" : "text-slate-600"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        {/* Top Navbar Right Actions: Bell + Action Buttons */}
        <div className="flex items-center gap-3">
          {/* Active Marine Alerts Bell Icon with Pulsing Badge */}
          <Link
            href="/alerts"
            className={`relative p-2 rounded-xl border transition-all flex items-center justify-center ${
              pathname === "/alerts"
                ? "bg-blue-50 text-[#0066CC] border-blue-200"
                : "bg-slate-50 border-slate-200 text-slate-600 hover:text-slate-900 hover:bg-slate-100"
            }`}
            title="Official Marine Alerts & Advisories"
          >
            <Bell size={18} />
            <span className="absolute -top-0.5 -right-0.5 flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500" />
            </span>
          </Link>

          {/* Top Navbar Action Buttons (Login & Try Demo) */}
          <div className="hidden sm:flex items-center gap-2.5">
            <Link
              href="/login"
              className="px-4 py-2 rounded-xl text-xs font-bold text-slate-700 hover:bg-slate-50 border border-slate-200 transition-colors shadow-2xs"
            >
              Login
            </Link>

            <Link
              href="/select-role"
              className="px-5 py-2 rounded-xl bg-[#0066CC] hover:bg-[#0052A3] text-white font-extrabold text-xs tracking-wide shadow-md shadow-blue-600/20 transition-all hover:scale-[1.02]"
            >
              Try Demo
            </Link>
          </div>

          {/* Mobile menu button */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-2 rounded-lg bg-surface-light border border-border text-text-muted"
          >
            {mobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileMenuOpen && (
        <div className="md:hidden border-b border-border bg-surface px-4 py-3 space-y-2">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setMobileMenuOpen(false)}
              className="block py-1.5 text-sm text-text-muted hover:text-cyan font-medium"
            >
              {link.label}
            </Link>
          ))}
          <div className="pt-2 border-t border-border/60 flex items-center gap-2">
            {isLoggedIn && user ? (
              <div className="flex items-center justify-between w-full">
                <span className="text-xs text-text-muted font-medium truncate">
                  {user.name || user.email}
                </span>
                <button
                  onClick={() => {
                    logout();
                    setMobileMenuOpen(false);
                  }}
                  className="px-3 py-1.5 rounded-lg bg-surface-light hover:bg-surface border border-border text-xs text-text-muted hover:text-avoid transition-colors"
                >
                  Logout
                </button>
              </div>
            ) : (
              <>
                <Link
                  href="/login"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex-1 text-center py-2 rounded-lg bg-surface-light border border-border text-xs font-semibold"
                >
                  Login
                </Link>
                <Link
                  href="/register"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex-1 text-center py-2 rounded-lg bg-cyan text-bg font-bold text-xs"
                >
                  Register
                </Link>
              </>
            )}
          </div>
        </div>
      )}
    </header>
  );
}