"use client";

import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
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
          © 2026 or. All rights reserved by ocenix .
        </footer>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-bg text-text-primary">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 h-screen">
        <TopBar />
        <main className="flex-1 overflow-y-auto pb-16 md:pb-0">{children}</main>
      </div>
    </div>
  );
}