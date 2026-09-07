import { AlertTriangle, CheckCircle2, CircleHelp, Clock3, Database, MapPin } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { formatNumber, formatTime, summarizeEvidence, type MarineSourceName } from "@/lib/formatters/marine";
import type { EvidenceItem } from "@/lib/schemas/journey";

const stateTone = { available: "success", degraded: "caution", pending: "info", unavailable: "danger", not_requested: "neutral" } as const;

export function EvidenceCard({ source, item, focused = false }: { source: MarineSourceName; item: EvidenceItem; focused?: boolean }) {
  const summary = summarizeEvidence(source, item);
  const Icon = item.state === "available" ? CheckCircle2 : item.state === "degraded" ? AlertTriangle : CircleHelp;
  return (
    <Card id={`evidence-${source}`} tabIndex={focused ? -1 : undefined} className={`min-w-0 p-3 ${focused ? "border-[var(--secondary)] ring-2 ring-[var(--secondary)]/25" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0"><h4 className="font-semibold">{summary.label}</h4><p className="font-data text-xl font-semibold">{formatNumber(summary.value)} <span className="text-sm font-normal">{summary.value === undefined ? "" : summary.unit}</span></p></div>
        <Badge tone={stateTone[item.state]}><Icon aria-hidden="true" className="size-3.5" />{item.state.replaceAll("_", " ")}</Badge>
      </div>
      {summary.direction && <p className="mt-2 text-sm"><strong>{summary.directionSemantics}:</strong> {summary.direction}</p>}
      <dl className="mt-2 grid gap-1 text-xs text-[var(--muted-foreground)]">
        <div className="flex gap-2"><Clock3 aria-hidden="true" className="size-4 shrink-0" /><dt className="sr-only">Valid time</dt><dd>{formatTime(summary.validTime)}</dd></div>
        <div className="flex gap-2"><Database aria-hidden="true" className="size-4 shrink-0" /><dt className="sr-only">Freshness</dt><dd>{summary.freshness ?? "No cache status"}</dd></div>
      </dl>
      <Accordion type="single" collapsible className="mt-2">
        <AccordionItem value="details" className="border-0"><AccordionTrigger className="text-sm">Source details</AccordionTrigger><AccordionContent>
          <dl className="space-y-2">
            <div><dt className="font-semibold">Provider</dt><dd>{summary.provider ?? "Not supplied"}</dd></div>
            <div><dt className="font-semibold">Product / dataset</dt><dd className="long-token font-data text-xs">{summary.product ?? "—"}<br />{summary.dataset ?? "—"}{summary.datasetVersion ? ` · ${summary.datasetVersion}` : ""}</dd></div>
            <div><dt className="font-semibold">Sampling</dt><dd>{summary.quality ?? "Not supplied"}{summary.distance !== undefined ? ` · ${formatNumber(summary.distance, 3)} km` : ""}</dd></div>
            {summary.sampledLatitude !== undefined && summary.sampledLongitude !== undefined && <div className="flex gap-2"><MapPin aria-hidden="true" className="mt-0.5 size-4 shrink-0" /><div><dt className="font-semibold">Sampled coordinate</dt><dd className="font-data">{summary.sampledLatitude}, {summary.sampledLongitude}</dd></div></div>}
            {summary.uncertainty !== undefined && <div><dt className="font-semibold">Uncertainty</dt><dd>{formatNumber(summary.uncertainty)}%</dd></div>}
            {summary.warnings.length > 0 && <div><dt className="font-semibold">Warnings</dt><dd><ul className="list-disc space-y-1 pl-5">{summary.warnings.map((warning) => <li className="long-token" key={warning}>{warning}</li>)}</ul></dd></div>}
            {summary.attribution && <div><dt className="font-semibold">Attribution</dt><dd className="long-token">{summary.attribution}</dd></div>}
          </dl>
        </AccordionContent></AccordionItem>
      </Accordion>
    </Card>
  );
}
