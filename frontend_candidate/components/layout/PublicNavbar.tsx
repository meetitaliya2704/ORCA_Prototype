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
    { href: "/about", label: "About" },
    { href: "/capabilities", label: "Capabilities" },
    { href: "/chat", label: "Dashboard" },
  ];

  return (
    <header className="sticky top-0 z-50 bg-white/85 backdrop-blur-md border-b border-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-cyan/10 border border-cyan/30 flex items-center justify-center overflow-hidden">
            <Image src="/brand/oceanix-logo.png" alt="Oceanix logo" width={36} height={36} className="w-full h-full object-cover object-top scale-125" />
          </div>
          <span className="font-display font-black text-lg tracking-wide text-text-primary">
            Oceanix
          </span>
        </Link>

        {/* Top Navbar Links (Home, Map, Alerts, Capabilities, About, Dashboard) */}
        <nav className="hidden md:flex items-center gap-7 text-sm font-medium">
          {navLinks.map((link) => {
            const isActive =
              link.href === "/chat"
                ? pathname === "/chat" || pathname === "/map" || pathname === "/alerts"
                : pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`transition-colors hover:text-cyan ${
                  isActive ? "text-cyan font-semibold" : "text-text-muted"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        {/* Top Navbar Right Actions: Bell + Action Buttons */}
        <div className="flex items-center gap-2.5">
          {/* Active Marine Alerts Bell Icon with Pulsing Badge */}
          <Link
            href="/alerts"
            className={`relative p-2 rounded-xl border transition-all flex items-center justify-center ${
              pathname === "/alerts"
                ? "bg-cyan/15 text-cyan border-cyan/40"
                : "bg-surface-light border-border text-text-muted hover:text-text-primary hover:bg-surface"
            }`}
            title="Official Marine Alerts & Advisories"
          >
            <Bell size={18} />
            <span className="absolute -top-0.5 -right-0.5 flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500" />
            </span>
          </Link>

          {/* Top Navbar Action Buttons (Login / Register / Dashboard) */}
          <div className="hidden md:flex items-center gap-3">
            {isLoggedIn && user ? (
              <div className="flex items-center gap-3">
                <Link
                  href="/chat"
                  className="px-3.5 py-1.5 rounded-lg bg-cyan text-bg font-bold text-xs hover:bg-cyan/90 transition-all flex items-center gap-1 shadow-md shadow-cyan/20"
                >
                  <span>Dashboard</span>
                  <ArrowRight size={13} />
                </Link>
                <button
                  onClick={logout}
                  className="px-3 py-1.5 rounded-lg bg-surface-light hover:bg-surface border border-border text-xs text-text-muted hover:text-avoid transition-colors"
                >
                  Logout
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <Link
                  href="/login"
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                    pathname === "/login"
                      ? "text-cyan bg-surface-light border border-cyan/30"
                      : "text-text-muted hover:text-text-primary"
                  }`}
                >
                  Login
                </Link>
                <Link
                  href="/register"
                  className="px-4 py-1.5 rounded-lg bg-cyan text-bg font-bold text-xs hover:bg-cyan/90 transition-all flex items-center gap-1.5 shadow-md shadow-cyan/20"
                >
                  <Sparkles size={13} />
                  <span>Register</span>
                </Link>
              </div>
            )}
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