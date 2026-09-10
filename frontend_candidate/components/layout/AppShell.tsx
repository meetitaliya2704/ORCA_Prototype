"use client";

import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";
import PublicNavbar from "./PublicNavbar";

const publicRoutes = ["/", "/about", "/capabilities", "/login", "/register"];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isPublic = publicRoutes.includes(pathname);

  if (isPublic) {
    return (
      <div className="min-h-screen flex flex-col bg-bg text-text-primary">
        <PublicNavbar />
        <main className="flex-1">{children}</main>
        <footer className="border-t border-border bg-white py-6 text-center text-sm text-text-muted">
          © 2026 ORCA. All rights reserved by Oceanix.
        </footer>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-bg text-text-primary">
      <PublicNavbar />
      <div className="flex flex-1 min-w-0 overflow-hidden">
        <Sidebar />
        <main className="flex-1 min-w-0 overflow-y-auto pb-16 md:pb-0">{children}</main>
      </div>
    </div>
  );
}