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
    <Card id={`evidence-${source}`} tabIndex={focused ? -1 : undefined} className={`min-w-0 overflow-hidden p-3 ${focused ? "border-[var(--secondary)] ring-2 ring-[var(--secondary)]/25" : ""}`}>
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1"><h4 className="break-words font-semibold">{summary.label}</h4><p className="font-data text-xl font-semibold break-words">{formatNumber(summary.value)} <span className="text-sm font-normal">{summary.value === undefined ? "" : summary.unit}</span></p></div>
        <Badge tone={stateTone[item.state]} className="shrink-0"><Icon aria-hidden="true" className="size-3.5" />{item.state.replaceAll("_", " ")}</Badge>
      </div>
      {summary.direction && <p className="mt-2 min-w-0 break-words text-sm"><strong>{summary.directionSemantics}:</strong> {summary.direction}</p>}
      <dl className="mt-2 grid min-w-0 gap-1 text-xs text-[var(--muted-foreground)]">
        <div className="flex min-w-0 gap-2"><Clock3 aria-hidden="true" className="size-4 shrink-0" /><dt className="sr-only">Valid time</dt><dd className="min-w-0 break-words">{formatTime(summary.validTime)}</dd></div>
        <div className="flex min-w-0 gap-2"><Database aria-hidden="true" className="size-4 shrink-0" /><dt className="sr-only">Freshness</dt><dd className="min-w-0 break-words">{summary.freshness ?? "No cache status"}</dd></div>
      </dl>
      <Accordion type="single" collapsible className="mt-2 min-w-0">
        <AccordionItem value="details" className="border-0"><AccordionTrigger className="text-sm">Source details</AccordionTrigger><AccordionContent className="min-w-0 overflow-hidden">
          <dl className="space-y-2 min-w-0">
            <div className="min-w-0"><dt className="font-semibold">Provider</dt><dd className="min-w-0 break-words">{summary.provider ?? "Not supplied"}</dd></div>
            <div className="min-w-0"><dt className="font-semibold">Product / dataset</dt><dd className="token-break long-token font-data text-xs break-all">{summary.product ?? "—"}<br />{summary.dataset ?? "—"}{summary.datasetVersion ? ` · ${summary.datasetVersion}` : ""}</dd></div>
            <div className="min-w-0"><dt className="font-semibold">Sampling</dt><dd className="min-w-0 break-words">{summary.quality ?? "Not supplied"}{summary.distance !== undefined ? ` · ${formatNumber(summary.distance, 3)} km` : ""}</dd></div>
            {summary.sampledLatitude !== undefined && summary.sampledLongitude !== undefined && <div className="flex min-w-0 gap-2"><MapPin aria-hidden="true" className="mt-0.5 size-4 shrink-0" /><div className="min-w-0"><dt className="font-semibold">Sampled coordinate</dt><dd className="font-data break-all">{summary.sampledLatitude}, {summary.sampledLongitude}</dd></div></div>}
            {summary.uncertainty !== undefined && <div className="min-w-0"><dt className="font-semibold">Uncertainty</dt><dd className="min-w-0 break-words">{formatNumber(summary.uncertainty)}%</dd></div>}
            {summary.warnings.length > 0 && <div className="min-w-0"><dt className="font-semibold">Warnings</dt><dd><ul className="list-disc space-y-1 pl-5 min-w-0">{summary.warnings.map((warning) => <li className="long-token min-w-0 break-words" key={warning}>{warning}</li>)}</ul></dd></div>}
            {summary.attribution && <div className="min-w-0"><dt className="font-semibold">Attribution</dt><dd className="long-token min-w-0 break-words">{summary.attribution}</dd></div>}
          </dl>
        </AccordionContent></AccordionItem>
      </Accordion>
    </Card>
  );
}
