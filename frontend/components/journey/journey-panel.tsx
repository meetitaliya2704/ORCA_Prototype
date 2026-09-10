import { AlertOctagon, Anchor, Compass, Fish, Gauge, MapPin } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { JourneyResponse } from "@/lib/schemas/journey";
import { formatTime } from "@/lib/formatters/marine";

const labels: Record<string, string> = {
  VALID_PFZ_FOUND: "A valid PFZ advisory was found.",
  NO_VALID_PFZ: "No PFZ advisory is valid for the requested time.",
  PFZ_DATA_PENDING: "PFZ data is refreshing.",
  PFZ_DATA_UNAVAILABLE: "PFZ advisory data is unavailable.",
  ORIGIN_LIMIT_EXCEEDED: "A supplied limit was exceeded at the origin.",
  DESTINATION_LIMIT_EXCEEDED: "A supplied limit was exceeded at the PFZ location.",
  ORIGIN_EVIDENCE_INSUFFICIENT: "Critical origin evidence is incomplete.",
  DESTINATION_EVIDENCE_INSUFFICIENT: "Critical PFZ-location evidence is incomplete.",
  ORIGIN_CAUTION: "An origin condition is near a supplied limit.",
  DESTINATION_CAUTION: "A PFZ-location condition is near a supplied limit.",
  WITHIN_CONFIGURED_LIMITS_AT_CHECKED_LOCATIONS: "Available conditions did not exceed supplied limits at the checked locations.",
  ROUTE_NOT_EVALUATED: "The straight line is a reference only; no route was evaluated.",
  GEOFENCES_NOT_EVALUATED: "Restricted areas and geofences were not evaluated.",
  OFFICIAL_WARNINGS_NOT_INTEGRATED: "Official warning coverage is not integrated.",
  PFZ_DOES_NOT_GUARANTEE_FISH_PRESENCE: "A PFZ advisory does not guarantee fish presence.",
};

function statusTone(status: JourneyResponse["journey_status"]) {
  if (status.includes("LIMIT_EXCEEDED") || status === "PFZ_SOURCE_UNAVAILABLE") return "danger";
  if (status.includes("CAUTION") || status.includes("INSUFFICIENT") || status === "POLICY_NOT_CONFIGURED") return "caution";
  if (status === "PFZ_REFRESH_PENDING") return "info";
  if (status === "NO_VALID_PFZ") return "neutral";
  return "success";
}

export function JourneyPanel({ result, demonstration }: { result: JourneyResponse | null; demonstration: boolean }) {
  if (!result) return <Card><CardHeader><h2 className="font-bold">PFZ journey and evidence</h2></CardHeader><CardContent className="text-center"><Anchor aria-hidden="true" className="mx-auto size-10 text-[var(--secondary)]" /><h3 className="mt-3 font-semibold">No journey checked yet</h3><p className="mt-1 text-sm text-[var(--muted-foreground)]">Supply your location and at least one operational limit. ORCA will keep PFZ validity separate from operational conditions.</p></CardContent></Card>;
  const pfz = result.pfz?.nearest_pfz;
  const depthMinimum = pfz?.depth_m?.minimum ?? pfz?.depth_min_m;
  const depthMaximum = pfz?.depth_m?.maximum ?? pfz?.depth_max_m;
  return (
    <Card className="min-w-0 overflow-hidden">
      <CardHeader><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-bold">Journey result</h2></div><Badge tone={statusTone(result.journey_status)} className="mt-2 max-w-full whitespace-normal text-left"><AlertOctagon aria-hidden="true" className="size-3.5 shrink-0" />{result.journey_status.replaceAll("_", " ")}</Badge></CardHeader>
      <CardContent className="space-y-4 min-w-0">
        {pfz ? <section className="min-w-0"><h3 className="flex items-center gap-2 font-semibold"><Fish aria-hidden="true" className="size-4 text-[var(--secondary)]" />Nearest valid PFZ</h3><dl className="mt-2 grid min-w-0 grid-cols-2 gap-x-3 gap-y-2 text-sm"><div className="min-w-0 overflow-hidden"><dt className="text-[var(--muted-foreground)]">Landing centre</dt><dd className="font-semibold break-words">{pfz.landing_centre}</dd></div><div className="min-w-0 overflow-hidden"><dt className="text-[var(--muted-foreground)]">Region</dt><dd className="break-words">{pfz.region_name}</dd></div><div className="min-w-0 overflow-hidden"><dt className="text-[var(--muted-foreground)]">Distance</dt><dd className="font-data break-words">{result.distance?.kilometres} km</dd></div><div className="min-w-0 overflow-hidden"><dt className="text-[var(--muted-foreground)]">Bearing</dt><dd className="font-data break-words">{result.distance?.bearing_degrees}° {result.distance?.direction}</dd></div><div className="min-w-0 overflow-hidden"><dt className="text-[var(--muted-foreground)]">Forecast date</dt><dd className="break-words">{result.pfz?.forecast_date}</dd></div><div className="min-w-0 overflow-hidden"><dt className="text-[var(--muted-foreground)]">Valid until</dt><dd className="break-words">{formatTime(result.pfz?.valid_until)}</dd></div><div className="min-w-0 overflow-hidden"><dt className="text-[var(--muted-foreground)]">Depth range</dt><dd className="break-words">{depthMinimum ?? "—"}–{depthMaximum ?? "—"} m</dd></div><div className="min-w-0 overflow-hidden"><dt className="text-[var(--muted-foreground)]">Sector</dt><dd className="font-data long-token break-all">{pfz.sector_code}</dd></div></dl></section> : <section className="rounded-md bg-[var(--surface-muted)] p-3 min-w-0"><h3 className="font-semibold">PFZ status</h3><p className="break-words">{result.pfz_resolution.failure?.message ?? "No valid PFZ was returned."}</p></section>}
        <section className="min-w-0"><h3 className="flex items-center gap-2 font-semibold"><Gauge aria-hidden="true" className="size-4" />Location assessments</h3><div className="mt-2 grid min-w-0 gap-2 sm:grid-cols-2 xl:grid-cols-1"><Assessment name="Origin" location={result.origin} icon={<MapPin aria-hidden="true" className="size-4" />} /><Assessment name="PFZ destination" location={result.destination} icon={<Compass aria-hidden="true" className="size-4" />} /></div></section>
        <section className="min-w-0"><h3 className="font-semibold">Why this result</h3><ul className="mt-2 space-y-2 min-w-0 text-sm">{result.reason_codes.map((code) => <li className="flex min-w-0 gap-2 overflow-hidden" key={code}><span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-[var(--secondary)]" /><span className="long-token min-w-0 flex-1 break-words"><strong className="font-data text-xs break-all">{code}</strong><br /><span className="break-words">{labels[code] ?? result.reasons.find((reason) => reason.code === code)?.message}</span></span></li>)}</ul></section>
      </CardContent>
    </Card>
  );
}

function Assessment({ name, location, icon }: { name: string; location: JourneyResponse["destination"] | JourneyResponse["origin"] | null; icon: React.ReactNode }) {
  return <div className="rounded-md border border-[var(--border)] p-3"><h4 className="flex items-center gap-2 font-semibold">{icon}{name}</h4>{location?.assessment ? <><p className="mt-1 font-data text-sm">{location.assessment.outcome.replaceAll("_", " ")}</p><p className="mt-1 text-xs text-[var(--muted-foreground)]">Evidence confidence: {location.assessment.evidence_confidence}</p></> : <p className="mt-1 text-sm text-[var(--muted-foreground)]">Evidence unavailable</p>}</div>;
}
