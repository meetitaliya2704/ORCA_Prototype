"use client";

import { ChevronDown, Clock3, Crosshair, Gauge, MapPin } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  assistantContextValuesSchema,
  type AssistantContextValues,
} from "@/lib/schemas/assistant-api";

const labels: Record<keyof AssistantContextValues, string> = {
  latitude: "Latitude",
  longitude: "Longitude",
  requestedTimeLocal: "Requested time",
  waveLimit: "Maximum significant wave height",
  windLimit: "Maximum wind speed",
  currentLimit: "Maximum surface-current speed",
};

export function AssistantContextPanel({
  values,
  onChange,
  missingFields = [],
  open,
  onOpenChange,
}: {
  values: AssistantContextValues;
  onChange: (values: AssistantContextValues) => void;
  missingFields?: ("location" | "requested_time" | "operational_limits")[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const issues = useMemo(() => assistantContextValuesSchema.safeParse(values), [values]);
  const errors = new Map(
    issues.success ? [] : issues.error.issues.map((issue) => [String(issue.path[0]), issue.message]),
  );
  const update = (key: keyof AssistantContextValues, value: string) => onChange({ ...values, [key]: value });
  const hasLocation = Boolean(values.latitude.trim() && values.longitude.trim());
  const limitCount = [values.waveLimit, values.windLimit, values.currentLimit].filter((value) => value.trim()).length;

  const useLocation = () => {
    if (!navigator.geolocation) {
      setTouched(new Set([...touched, "latitude"]));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => onChange({ ...values, latitude: String(coords.latitude), longitude: String(coords.longitude) }),
      () => setTouched(new Set([...touched, "latitude"])),
    );
  };

  const field = (
    key: keyof AssistantContextValues,
    unit: string,
    props: React.InputHTMLAttributes<HTMLInputElement> = {},
  ) => {
    const showError = touched.has(key) && errors.has(key);
    return <div className="min-w-0">
      <label htmlFor={`assistant-${key}`} className="mb-1 block text-xs font-bold text-[var(--foreground)]">
        {labels[key]} <span className="font-normal text-[var(--muted-foreground)]">({unit})</span>
      </label>
      <input
        id={`assistant-${key}`}
        value={values[key]}
        onChange={(event) => update(key, event.target.value)}
        onBlur={() => setTouched((current) => new Set([...current, key]))}
        aria-invalid={showError}
        aria-describedby={showError ? `assistant-${key}-error` : undefined}
        className="assistant-context-input"
        {...props}
      />
      {showError && <p id={`assistant-${key}-error`} role="alert" className="mt-1 text-xs font-semibold text-[var(--danger)]">{errors.get(key)}</p>}
    </div>;
  };

  return <section className="assistant-context" aria-labelledby="assistant-context-heading">
    <button
      type="button"
      className="assistant-context-toggle"
      aria-expanded={open}
      aria-controls="assistant-context-fields"
      onClick={() => onOpenChange(!open)}
    >
      <span className="flex min-w-0 items-center gap-2">
        <Gauge aria-hidden="true" className="size-4 shrink-0 text-[var(--secondary)]" />
        <span id="assistant-context-heading" className="font-bold">Query context</span>
      </span>
      <span className="ml-auto hidden min-w-0 items-center gap-2 text-xs font-medium text-[var(--muted-foreground)] sm:flex">
        <span>{hasLocation ? "Location ready" : "No location"}</span>
        <span aria-hidden="true">·</span>
        <span>{limitCount ? `${limitCount} limit${limitCount === 1 ? "" : "s"}` : "No limits"}</span>
      </span>
      <ChevronDown aria-hidden="true" className={`size-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
    </button>
    {open && <div id="assistant-context-fields" className="border-t border-[var(--border)] p-3">
      {missingFields.length > 0 && <div role="status" className="mb-3 rounded-lg border border-[var(--caution-border)] bg-[var(--caution-surface)] p-3 text-sm">
        <strong>ORCA needs more context.</strong>
        <p className="mt-1 text-[var(--muted-foreground)]">Add: {missingFields.map((item) => item.replaceAll("_", " ")).join(", ")}.</p>
      </div>}
      <div className="grid gap-3 sm:grid-cols-2">
        {field("latitude", "decimal degrees", { inputMode: "decimal", placeholder: "20.5000" })}
        {field("longitude", "decimal degrees", { inputMode: "decimal", placeholder: "72.9000" })}
      </div>
      <Button type="button" variant="secondary" className="mt-3 w-full" onClick={useLocation}>
        <Crosshair aria-hidden="true" className="size-4" />Use browser location
      </Button>
      <div className="my-3 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.08em] text-[var(--muted-foreground)]">
        <Clock3 aria-hidden="true" className="size-4" />Time and user-supplied limits
      </div>
      {field("requestedTimeLocal", "local timezone", { type: "datetime-local" })}
      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        {field("waveLimit", "m", { inputMode: "decimal", placeholder: "Optional" })}
        {field("windLimit", "m/s", { inputMode: "decimal", placeholder: "Optional" })}
        {field("currentLimit", "m/s", { inputMode: "decimal", placeholder: "Optional" })}
      </div>
      <p className="mt-3 flex items-start gap-2 text-xs text-[var(--muted-foreground)]">
        <MapPin aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />ORCA never invents a location or vessel limit. These limits are not authority-issued thresholds.
      </p>
    </div>}
  </section>;
}
