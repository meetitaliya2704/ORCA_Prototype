"use client";

import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";
import PublicNavbar from "./PublicNavbar";

const publicRoutes = ["/", "/about", "/capabilities", "/login", "/register", "/select-role"];
const dashboardRoutes = ["/dashboard", "/why-orca"];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isPublic = publicRoutes.includes(pathname);
  const isDashboard = dashboardRoutes.includes(pathname);

  if (isDashboard) {
    return (
      <div className="min-h-screen flex flex-col bg-[#F8FAFC] text-text-primary">
        <PublicNavbar />
        <main className="flex-1">{children}</main>
        <footer className="border-t border-slate-200 bg-white py-5 text-center text-xs text-slate-500 font-medium">
          © 2026 Oceanix Marine Decision-Support Platform.
        </footer>
      </div>
    );
  }

  if (isPublic) {
    return (
      <div className="min-h-screen flex flex-col bg-bg text-text-primary">
        <PublicNavbar />
        <main className="flex-1">{children}</main>
        <footer className="border-t border-slate-200 bg-white py-6 text-center text-xs text-slate-500 font-medium">
          © 2026 Oceanix. All rights reserved.
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