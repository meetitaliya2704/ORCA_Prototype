import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const tones = {
  neutral: "bg-[var(--surface-muted)] text-[var(--foreground)]",
  info: "bg-blue-100 text-blue-900",
  success: "bg-[var(--success-surface)] text-[var(--success)]",
  caution: "bg-[var(--caution-surface)] text-[var(--caution)]",
  danger: "bg-[var(--danger-surface)] text-[var(--danger)]",
} as const;

export function Badge({ tone = "neutral", className, ...props }:
  HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof tones }) {
  return <span className={cn("inline-flex min-h-6 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold", tones[tone], className)} {...props} />;
}
