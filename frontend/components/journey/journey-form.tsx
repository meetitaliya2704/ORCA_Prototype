"use client";

import { Crosshair, FlaskConical, LoaderCircle, MapPin, Navigation, X } from "lucide-react";
import { useRef, useState } from "react";
import type { ZodIssue } from "zod";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { formValuesToRequest, journeyFormSchema, type JourneyFormValues } from "@/lib/schemas/form";
import type { JourneyRequest } from "@/lib/schemas/journey";

const initialValues: JourneyFormValues = {
  latitude: "",
  longitude: "",
  atLocal: "",
  waveLimit: "",
  windLimit: "",
  currentLimit: "",
};

const fieldLabels: Record<string, string> = {
  latitude: "Latitude",
  longitude: "Longitude",
  atLocal: "Requested time",
  waveLimit: "Maximum significant wave height",
  windLimit: "Maximum wind speed",
  currentLimit: "Maximum current speed",
  operational_limits: "Operational limits",
};

export function JourneyForm({
  onSubmit,
  onDemo,
  onCancel,
  submitting,
  demoEnabled,
  onValidationIssues,
}: {
  onSubmit: (request: JourneyRequest) => void;
  onDemo: () => void;
  onCancel: () => void;
  submitting: boolean;
  demoEnabled: boolean;
  onValidationIssues?: (missing: ("location" | "operational_limits")[]) => void;
}) {
  const [values, setValues] = useState(initialValues);
  const [issues, setIssues] = useState<ZodIssue[]>([]);
  const errorSummary = useRef<HTMLDivElement>(null);
  const errors = new Map(issues.map((issue) => [String(issue.path[0]), issue.message]));

  const update = (key: keyof JourneyFormValues, value: string) => setValues((current) => ({ ...current, [key]: value }));
  const validateAndSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const parsed = journeyFormSchema.safeParse(values);
    if (!parsed.success) {
      setIssues(parsed.error.issues);
      const missing: ("location" | "operational_limits")[] = [];
      if (parsed.error.issues.some((issue) => issue.path[0] === "latitude" || issue.path[0] === "longitude")) missing.push("location");
      if (parsed.error.issues.some((issue) => issue.path[0] === "operational_limits" || ["waveLimit", "windLimit", "currentLimit"].includes(String(issue.path[0])))) missing.push("operational_limits");
      if (missing.length) onValidationIssues?.(missing);
      window.setTimeout(() => errorSummary.current?.focus(), 0);
      return;
    }
    setIssues([]);
    onSubmit(formValuesToRequest(parsed.data));
  };
  const usePosition = () => {
    if (!navigator.geolocation) {
      setIssues([{ code: "custom", path: ["latitude"], message: "Geolocation is not available in this browser." }]);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => setValues((current) => ({ ...current, latitude: String(coords.latitude), longitude: String(coords.longitude) })),
      () => setIssues([{ code: "custom", path: ["latitude"], message: "Location permission was not granted." }]),
    );
  };
  const loadExample = () => {
    setValues({ latitude: "20.5", longitude: "72.9", atLocal: "", waveLimit: "2", windLimit: "12", currentLimit: "1" });
    setIssues([]);
  };
  const input = (id: keyof JourneyFormValues, label: string, unit?: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-semibold">{label}{unit && <span className="font-normal text-[var(--muted-foreground)]"> ({unit})</span>}</label>
      <input id={id} value={values[id]} onChange={(event) => update(id, event.target.value)} aria-invalid={errors.has(id)} aria-describedby={`${id}-help ${id}-error`} className="min-h-11 w-full rounded-md border border-[var(--border)] bg-white px-3 py-2 font-data text-base text-[var(--foreground)] aria-invalid:border-[var(--danger)]" {...props} />
      {props.title && <p id={`${id}-help`} className="mt-1 text-xs text-[var(--muted-foreground)]">{props.title}</p>}
      {errors.has(id) && <p id={`${id}-error`} role="alert" className="mt-1 text-sm font-medium text-[var(--danger)]">{errors.get(id)}</p>}
    </div>
  );

  return (
    <Card>
      <CardHeader><div className="flex items-center gap-2"><Navigation aria-hidden="true" className="size-5 text-[var(--secondary)]" /><h2 className="font-bold">PFZ journey query</h2></div><p className="mt-1 text-sm text-[var(--muted-foreground)]">Compare origin and nearest valid PFZ conditions against limits you supply.</p></CardHeader>
      <CardContent>
        <form noValidate onSubmit={validateAndSubmit}>
          {issues.length > 0 && <div ref={errorSummary} tabIndex={-1} role="alert" aria-labelledby="query-error-title" className="mb-4 rounded-md border border-red-300 bg-[var(--danger-surface)] p-3"><h3 id="query-error-title" className="font-bold text-[var(--danger)]">Check the journey query</h3><ul className="mt-1 list-disc pl-5 text-sm">{issues.map((issue, index) => <li key={`${issue.path.join("-")}-${index}`}><a href={`#${String(issue.path[0])}`}>{fieldLabels[String(issue.path[0])] ?? "Request"}: {issue.message}</a></li>)}</ul></div>}
          <fieldset className="space-y-3"><legend className="mb-2 font-semibold">Origin</legend>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">{input("latitude", "Latitude", "decimal degrees", { inputMode: "decimal", title: "-90 to 90" })}{input("longitude", "Longitude", "decimal degrees", { inputMode: "decimal", title: "-180 to 180" })}</div>
            <Button type="button" variant="secondary" className="w-full" onClick={usePosition}><Crosshair aria-hidden="true" className="size-4" />Use my location</Button>
          </fieldset>
          <fieldset className="mt-5 space-y-3"><legend className="mb-2 font-semibold">Time and operational limits</legend>
            {input("atLocal", "Requested time", "your local timezone", { type: "datetime-local", title: "Leave empty to use the current time once for the complete request." })}
            {input("waveLimit", "Maximum significant wave height", "m", { inputMode: "decimal", title: "Optional user-supplied limit; not an official vessel threshold." })}
            {input("windLimit", "Maximum wind speed", "m/s", { inputMode: "decimal", title: "Optional user-supplied limit; wind direction remains direction-from." })}
            {input("currentLimit", "Maximum surface-current speed", "m/s", { inputMode: "decimal", title: "Optional user-supplied limit; current direction remains direction-toward." })}
          </fieldset>
          <div className="mt-5 grid gap-2">
            <Button type="submit" disabled={submitting}>{submitting ? <LoaderCircle aria-hidden="true" className="size-4 animate-spin" /> : <MapPin aria-hidden="true" className="size-4" />}{submitting ? "Collecting evidence…" : "Find nearest PFZ"}</Button>
            {submitting && <Button type="button" variant="secondary" onClick={onCancel}><X aria-hidden="true" className="size-4" />Cancel request</Button>}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
