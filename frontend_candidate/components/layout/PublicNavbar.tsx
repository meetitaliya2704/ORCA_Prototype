"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Waves, Sparkles, ArrowRight, Menu, X } from "lucide-react";
import { useUserMode } from "@/lib/context";
import { useState } from "react";

export default function PublicNavbar() {
  const pathname = usePathname();
  const { user, isLoggedIn, logout } = useUserMode();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navLinks = [
    { href: "/", label: "Home" },
    { href: "/about", label: "About" },
    { href: "/#features", label: "Capabilities" },
    { href: "/dashboard", label: "Live Platform" },
  ];

  return (
    <header className="sticky top-0 z-50 bg-white/85 backdrop-blur-md border-b border-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-cyan/10 border border-cyan/30 flex items-center justify-center">
            <Waves className="text-cyan" size={20} />
          </div>
          <span className="font-display font-black text-lg tracking-[0.18em] text-text-primary uppercase">
            ocenix
          </span>
        </Link>

        {/* Top Navbar Links (Home, About, Capabilities) */}
        <nav className="hidden md:flex items-center gap-8 text-sm font-medium">
          {navLinks.map((link) => {
            const isActive = pathname === link.href;
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

        {/* Top Navbar Action Buttons (Login / Register) */}
        <div className="hidden md:flex items-center gap-3">
          {isLoggedIn && user ? (
            <div className="flex items-center gap-3">
              <Link
                href="/dashboard"
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
          </div>
        </div>
      )}
    </header>
  );
}