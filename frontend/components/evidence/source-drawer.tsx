import { AlertTriangle, BookOpen, Database } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Card, CardContent } from "@/components/ui/card";
import { summarizeEvidence, type MarineSourceName } from "@/lib/formatters/marine";
import type { JourneyResponse } from "@/lib/schemas/journey";

const marineSources: MarineSourceName[] = ["sst", "chlorophyll", "waves", "wind", "currents", "sea_level"];

export function SourceDrawer({ result }: { result: JourneyResponse | null }) {
  const evidence = [result?.origin.evidence, result?.destination?.evidence].filter(Boolean);
  const failures = evidence.flatMap((bundle) => bundle?.failures ?? []);
  const sourceDetails = Array.from(
    new Map(
      evidence.flatMap((bundle) => marineSources.map((source) => {
        const summary = summarizeEvidence(source, bundle!.evidence[source]);
        return [`${source}:${summary.dataset ?? summary.provider ?? "unknown"}`, { source, summary }] as const;
      })),
    ).values(),
  );
  return (
    <Card className="sources-panel">
      <CardContent>
        <Accordion type="single" collapsible>
          <AccordionItem value="sources" className="border-0">
            <AccordionTrigger><span className="flex items-center gap-2"><Database aria-hidden="true" className="size-5 text-[var(--secondary)]" />Sources, warnings, and prototype limitations</span></AccordionTrigger>
            <AccordionContent>
              <div className="grid gap-4 lg:grid-cols-3">
                <section><h3 className="flex items-center gap-2 font-semibold"><BookOpen aria-hidden="true" className="size-4" />Source provenance</h3><ul className="mt-2 space-y-2 text-sm"><li>INCOIS Potential Fishing Zone advisories</li>{sourceDetails.map(({ source, summary }) => <li className="long-token" key={`${source}-${summary.dataset ?? summary.provider}`}><strong>{summary.label}</strong>: {summary.provider ?? "Provider preserved in evidence"}{summary.dataset && <><br /><code className="font-data text-xs">{summary.dataset}</code></>}</li>)}</ul></section>
                <section><h3 className="flex items-center gap-2 font-semibold"><AlertTriangle aria-hidden="true" className="size-4" />Current coverage</h3><ul className="mt-2 list-disc space-y-1 pl-5 text-sm"><li>Official warning coverage: not integrated</li><li>Reference line: route not evaluated</li><li>Geofences and route hazards: not evaluated</li>{failures.map((failure) => <li key={`${failure.source}-${failure.code}`}>{failure.source}: {failure.message}</li>)}</ul></section>
                <section className="rounded-md border border-amber-300 bg-[var(--caution-surface)] p-3"><h3 className="font-bold">Decision-support limitation</h3><p className="mt-1 text-sm">ORCA is an educational decision-support prototype. It is not certified navigation advice. Official meteorological and maritime warnings are not fully integrated and must be verified independently.</p></section>
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </CardContent>
    </Card>
  );
}
