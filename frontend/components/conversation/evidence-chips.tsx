import { Database } from "lucide-react";
import type { EvidenceReference } from "@/lib/schemas/assistant";

export function EvidenceChips({ references, onSelect }: { references: EvidenceReference[]; onSelect: (reference: EvidenceReference) => void }) {
  if (!references.length) return null;
  return <div className="mt-3 flex flex-wrap gap-2" aria-label="Evidence references">{references.map((reference, index) => <button key={`${reference.location}-${reference.source}-${index}`} type="button" onClick={() => onSelect(reference)} className="min-h-11 cursor-pointer rounded-full border border-[var(--border)] bg-white px-3 py-1.5 text-left text-xs transition-colors hover:border-[var(--secondary)] focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]"><span className="flex items-center gap-1.5 font-semibold"><Database aria-hidden="true" className="size-3.5" />{reference.label}</span><span className="block text-[var(--muted-foreground)]">{reference.location} · {reference.state}{reference.freshness ? ` · ${reference.freshness}` : ""}</span></button>)}</div>;
}
