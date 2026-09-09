import Link from "next/link";
import {
  Waves,
  ShieldCheck,
  Compass,
  Cpu,
  Radio,
  ArrowRight,
  Anchor,
} from "lucide-react";

export default function AboutPage() {
  const agents = [
    {
      name: "Marine Data Agent",
      role: "Buoy and Sensor Telemetry",
      desc: "Ingests live feeds from INCOIS coastal buoys, tide gauge stations, and acoustic bathymetry maps.",
      icon: Radio,
    },
    {
      name: "Meteorological Agent",
      role: "Atmospheric and Doppler Radar",
      desc: "Processes real-time IMD radar reflectivity, ECMWF high-resolution models, and GFS wind vectors.",
      icon: Waves,
    },
    {
      name: "Ocean Analytics Agent",
      role: "Hydrodynamics and Currents",
      desc: "Solves sea surface temperature anomalies, salinity fronts, wave-surge physics, and swell propagation.",
      icon: Cpu,
    },
    {
      name: "GIS and Spatial Agent",
      role: "Boundary and Corridor Verification",
      desc: "Cross-checks nautical channels against marine sanctuaries, international borders, and shoal hazards.",
      icon: Compass,
    },
    {
      name: "Risk Consensus Agent",
      role: "Autonomous GO / WAIT / AVOID Arbiter",
      desc: "Synthesizes multi-agent evidence into a verifiable, deterministic safety score and clear recommendation.",
      icon: ShieldCheck,
    },
  ];

  return (
    <div className="py-12 px-4 sm:px-6 lg:px-8 max-w-6xl mx-auto space-y-16">
      <div className="text-center max-w-3xl mx-auto space-y-4">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-cyan/10 border border-cyan/30 text-cyan text-xs font-semibold uppercase tracking-wider">
          <Waves size={14} />
          <span>About ORCA Platform</span>
        </div>
        <h1 className="font-display font-black text-3xl sm:text-5xl text-text-primary tracking-tight">
          Next-Generation Autonomous <span className="text-cyan">Marine Intelligence</span>
        </h1>
        <p className="text-text-muted text-sm sm:text-base leading-relaxed">
          ORCA combines real-time oceanographic sensor telemetry, satellite feeds, and a collaborative network of autonomous AI agents to deliver instant, verifiable GO / WAIT / AVOID maritime decisions.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="p-6 rounded-3xl bg-surface border border-border space-y-3">
          <div className="w-10 h-10 rounded-xl bg-cyan/10 border border-cyan/30 flex items-center justify-center text-cyan">
            <Anchor size={20} />
          </div>
          <h3 className="font-display font-bold text-xl text-text-primary">Our Mission</h3>
          <p className="text-text-muted text-sm leading-relaxed">
            Every year, thousands of coastal fishermen and commercial vessels encounter sudden severe weather, rough sea swells, and unpredicted squalls. Our mission is to democratize high-resolution ocean intelligence, ensuring every seafarer returns home safely.
          </p>
        </div>

        <div className="p-6 rounded-3xl bg-surface border border-border space-y-3">
          <div className="w-10 h-10 rounded-xl bg-go/10 border border-go/30 flex items-center justify-center text-go">
            <ShieldCheck size={20} />
          </div>
          <h3 className="font-display font-bold text-xl text-text-primary">Verifiable Transparency</h3>
          <p className="text-text-muted text-sm leading-relaxed">
            Unlike opaque black-box AI, ORCA operates on strict evidence provenance. Every GO / WAIT / AVOID decision card links directly to timestamped buoy readings, Doppler radar passes, and confidence calibration metrics.
          </p>
        </div>
      </div>

      <div className="space-y-6">
        <div className="text-center max-w-2xl mx-auto">
          <h2 className="font-display font-bold text-2xl sm:text-3xl text-text-primary">
            Collaborative Multi-Agent Architecture
          </h2>
          <p className="text-text-muted text-xs sm:text-sm mt-1">
            Five specialized autonomous agents work concurrently to validate coastal safety
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {agents.map((agent, i) => {
            const Icon = agent.icon;
            return (
              <div
                key={agent.name}
                className={`p-5 rounded-2xl border bg-surface space-y-2.5 ${
                  i === 4 ? "md:col-span-2 border-cyan/40 bg-cyan/5" : "border-border"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="w-9 h-9 rounded-xl bg-surface-light border border-border flex items-center justify-center text-cyan">
                    <Icon size={18} />
                  </div>
                  <span className="text-[10px] font-mono text-text-muted">Agent 0{i + 1}</span>
                </div>
                <h4 className="font-display font-bold text-base text-text-primary">{agent.name}</h4>
                <p className="text-xs text-cyan font-mono">{agent.role}</p>
                <p className="text-xs text-text-muted leading-relaxed">{agent.desc}</p>
              </div>
            );
          })}
        </div>
      </div>

      <div className="p-8 sm:p-10 rounded-3xl bg-gradient-to-r from-surface via-surface-light to-surface border border-cyan/30 text-center space-y-4">
        <h3 className="font-display font-black text-2xl sm:text-3xl text-text-primary">
          Experience ORCA in Real Time
        </h3>
        <p className="text-text-muted text-sm max-w-xl mx-auto">
          Sign in or try our instant interactive demo across Fisherman, Port Authority, Researcher, and Fleet Operator modes.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
          <Link
            href="/login"
            className="px-6 py-3 rounded-xl bg-cyan text-bg font-bold text-sm hover:bg-cyan/90 transition-all flex items-center gap-2 shadow-lg shadow-cyan/20"
          >
            <span>Launch Live Platform</span>
            <ArrowRight size={16} />
          </Link>
          <Link
            href="/register"
            className="px-6 py-3 rounded-xl bg-surface-light hover:bg-surface border border-border text-sm font-semibold text-text-primary transition-colors"
          >
            Register Account
          </Link>
        </div>
      </div>
    </div>
  );
}