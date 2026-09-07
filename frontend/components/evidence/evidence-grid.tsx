import { EvidenceCard } from "./evidence-card";
import type { MarineEvidence } from "@/lib/schemas/journey";
import type { MarineSourceName } from "@/lib/formatters/marine";

const sources: MarineSourceName[] = ["sst", "chlorophyll", "waves", "wind", "currents", "sea_level"];

export function EvidenceGrid({ evidence, focusedSource }: { evidence: MarineEvidence; focusedSource?: MarineSourceName | null }) {
  return <div className="grid gap-3">{sources.map((source) => <EvidenceCard key={source} source={source} item={evidence.evidence[source]} focused={focusedSource === source} />)}</div>;
}
