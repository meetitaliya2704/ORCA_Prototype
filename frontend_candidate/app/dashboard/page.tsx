"use client";

import { useUserMode } from "@/lib/context";
import DashboardHeader from "@/components/dashboard/DashboardHeader";
import FishermanDashboardView from "@/components/dashboard/FishermanDashboardView";
import PortAuthorityDashboardView from "@/components/dashboard/PortAuthorityDashboardView";
import ResearcherDashboardView from "@/components/dashboard/ResearcherDashboardView";
import FleetOperatorDashboardView from "@/components/dashboard/FleetOperatorDashboardView";

export default function DashboardPage() {
  const { mode } = useUserMode();

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex flex-col">
      {/* Top Interactive Persona Header */}
      <DashboardHeader />

      {/* Main Dynamic View for Active Stakeholder */}
      <main className="flex-1 pb-16">
        {mode === "fisherman" && <FishermanDashboardView />}
        {mode === "authority" && <PortAuthorityDashboardView />}
        {mode === "researcher" && <ResearcherDashboardView />}
        {mode === "operator" && <FleetOperatorDashboardView />}
      </main>
    </div>
  );
}

