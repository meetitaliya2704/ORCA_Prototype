import { AlertTriangle, Anchor, Bot, CheckCircle2, CircleHelp, Database, MapPin, Route } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { formatTime } from "@/lib/formatters/marine";
import type { AssistantApiResponse, AssistantSourceSummary } from "@/lib/schemas/assistant-api";

const sourceLabels = {
  sst: "Sea surface temperature",
  chlorophyll: "Chlorophyll-a",
  waves: "Significant waves",
  wind: "Wind",
  currents: "Surface currents",
  sea_level: "Sea level",
} as const;

function responseTone(response: AssistantApiResponse) {
  if (response.completion_status === "failed" || response.evidence_summary.assessment_outcome === "LIMIT_EXCEEDED") return "danger" as const;
  if (response.completion_status === "partial" || response.completion_status === "clarification_required" || response.evidence_summary.evidence_confidence === "DEGRADED" || response.evidence_summary.evidence_confidence === "INSUFFICIENT") return "caution" as const;
  if (response.completion_status === "capability_not_available") return "neutral" as const;
  return "success" as const;
}

function sourceTone(state: AssistantSourceSummary["state"]) {
  return state === "available" ? "success" as const : state === "degraded" ? "caution" as const : state === "pending" ? "info" as const : "danger" as const;
}

export function AssistantResultPanel({ response }: { response: AssistantApiResponse | null }) {
  if (!response) return <Card className="answer-empty overflow-hidden">
    <CardContent className="relative flex min-h-72 flex-col items-center justify-center overflow-hidden px-6 py-12 text-center">
      <div className="sonar-rings" aria-hidden="true" />
      <div className="relative flex size-14 items-center justify-center rounded-2xl bg-[var(--primary)] text-white shadow-[var(--shadow-lg)]"><Bot aria-hidden="true" className="size-7" /></div>
      <h2 className="relative mt-5 text-xl font-bold">Evidence-backed answers appear here</h2>
      <p className="relative mt-2 max-w-md text-sm text-[var(--muted-foreground)]">Ask ORCA a question or use Advanced query parameters. Results remain understandable without opening the map.</p>
      <div className="relative mt-5 flex flex-wrap justify-center gap-2 text-xs">
        <Badge tone="neutral">PFZ validity</Badge><Badge tone="neutral">Marine conditions</Badge><Badge tone="neutral">Operational limits</Badge><Badge tone="neutral">Source provenance</Badge>
      </div>
    </CardContent>
  </Card>;

  const destination = findDestination(response);
  return <div className="space-y-3" aria-live="polite">
    <Card className="overflow-hidden">
      <div className="h-1 bg-[var(--secondary)]" aria-hidden="true" />
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.12em] text-[var(--secondary)]">ORCA Analysis</p>
            <h2 className="mt-1 text-lg font-bold">Analysis Result</h2>
          </div>
          {response.completion_status !== "capability_not_available" && <Badge tone={responseTone(response)} className="max-w-full whitespace-normal text-left">{response.completion_status === "completed" ? "Complete" : response.completion_status === "partial" ? "Partial data" : response.completion_status === "clarification_required" ? "More info needed" : "Error"}</Badge>}
        </div>
      </CardHeader>
      <CardContent className="min-w-0">
        <p className="min-w-0 break-words whitespace-pre-wrap text-[0.95rem] leading-7">{response.answer}</p>
        <dl className="mt-4 grid min-w-0 gap-2 sm:grid-cols-2">
          <Metric label="Operational outcome" value={response.evidence_summary.assessment_outcome?.replaceAll("_", " ") ?? "Not evaluated"} />
          <Metric label="Evidence confidence" value={response.evidence_summary.evidence_confidence ?? "Not evaluated"} />
        </dl>
      </CardContent>
    </Card>

    {destination && <Card className="overflow-hidden">
      <CardHeader><h3 className="flex items-center gap-2 font-bold"><Anchor aria-hidden="true" className="size-4 text-[var(--secondary)]" />PFZ destination</h3></CardHeader>
      <CardContent><dl className="grid min-w-0 gap-3 text-sm sm:grid-cols-2">
        <Metric label="Landing centre" value={destination.landingCentre ?? "Not supplied"} />
        <Metric label="Region" value={destination.region ?? "Not supplied"} />
        <Metric label="Coordinates" value={`${destination.latitude.toFixed(4)}, ${destination.longitude.toFixed(4)}`} mono />
        <Metric label="Sector" value={destination.sector ?? "Not supplied"} mono />
      </dl></CardContent>
    </Card>}

    <Card className="overflow-hidden">
      <CardHeader><div className="flex items-center justify-between gap-3"><h3 className="flex items-center gap-2 font-bold"><Database aria-hidden="true" className="size-4 text-[var(--secondary)]" />Marine evidence summary</h3><span className="text-xs text-[var(--muted-foreground)]">{response.evidence_summary.available_sources + response.evidence_summary.degraded_sources} usable</span></div></CardHeader>
      <CardContent className="grid min-w-0 gap-2 sm:grid-cols-2">
        {(Object.keys(sourceLabels) as (keyof typeof sourceLabels)[]).map((source) => {
          const item = response.sources.find((candidate) => candidate.source === source);
          const Icon = item?.state === "available" ? CheckCircle2 : item?.state === "degraded" ? AlertTriangle : CircleHelp;
          return <article key={source} className="min-w-0 overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface-raised)] p-3">
            <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
              <h4 className="min-w-0 break-words text-sm font-bold">{sourceLabels[source]}</h4>
              <Badge tone={item ? sourceTone(item.state) : "neutral"} className="shrink-0"><Icon aria-hidden="true" className="size-3.5" />{item?.state ?? "not collected"}</Badge>
            </div>
            <p className="mt-2 min-w-0 break-words text-xs text-[var(--muted-foreground)]">{item?.provider ?? "Provider pending"}</p>
            {(item?.dataset_id ?? item?.product_id) && <p className="token-break long-token mt-1 font-data text-[0.7rem] text-[var(--muted-foreground)] break-all">{item?.dataset_id ?? item?.product_id}</p>}
            {item?.valid_time && <p className="mt-2 min-w-0 break-words text-xs">Valid: {formatTime(item.valid_time)}</p>}
            {item?.freshness && <p className="mt-1 min-w-0 break-words text-xs">Data state: {item.freshness}</p>}
          </article>;
        })}
      </CardContent>
    </Card>

    {response.warnings.length > 0 && <Card className="overflow-hidden border-[var(--caution-border)]">
      <CardHeader><h3 className="flex items-center gap-2 font-bold"><AlertTriangle aria-hidden="true" className="size-4 text-[var(--caution)]" />Warnings and limitations</h3></CardHeader>
      <CardContent><ul className="space-y-2 min-w-0 text-sm">{response.warnings.map((warning) => <li key={warning.code} className="flex min-w-0 gap-2 overflow-hidden"><span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-[var(--caution)]" /><span className="long-token min-w-0 flex-1 break-words"><strong className="font-data text-xs break-all">{warning.code}</strong><br /><span className="break-words">{warning.message}</span></span></li>)}</ul></CardContent>
    </Card>}

  </div>;
}

function Metric({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="min-w-0 overflow-hidden"><dt className="truncate text-xs font-semibold text-[var(--muted-foreground)]">{label}</dt><dd className={`long-token mt-0.5 min-w-0 text-sm font-bold break-words ${mono ? "font-data break-all" : ""}`}>{value}</dd></div>;
}

function findDestination(response: AssistantApiResponse) {
  if (!response.geojson) return null;
  const features = response.geojson.type === "FeatureCollection" ? response.geojson.features : [response.geojson];
  const feature = features.find((item) => item.geometry.type === "Point" && (item.properties.feature_type === "pfz_destination" || "landing_centre" in item.properties));
  if (!feature || feature.geometry.type !== "Point") return null;
  return {
    longitude: feature.geometry.coordinates[0],
    latitude: feature.geometry.coordinates[1],
    landingCentre: typeof feature.properties.landing_centre === "string" ? feature.properties.landing_centre : null,
    region: typeof feature.properties.region_name === "string" ? feature.properties.region_name : null,
    sector: typeof feature.properties.sector_code === "string" ? feature.properties.sector_code : null,
  };
}
