"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Info, X } from "lucide-react";
import { Button } from "./button";

export function InformationDialog() {
  return (
    <DialogPrimitive.Root>
      <DialogPrimitive.Trigger asChild>
        <Button variant="ghost" size="icon" aria-label="About ORCA and its limitations"><Info aria-hidden="true" className="size-5" /></Button>
      </DialogPrimitive.Trigger>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-slate-950/55" />
        <DialogPrimitive.Content className="fixed left-1/2 top-1/2 z-50 max-h-[85dvh] w-[min(34rem,calc(100%-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl bg-white p-6 shadow-xl focus:outline-none">
          <div className="flex items-start justify-between gap-4">
            <div>
              <DialogPrimitive.Title className="text-xl font-bold">About this prototype</DialogPrimitive.Title>
              <DialogPrimitive.Description className="mt-2 text-[var(--muted-foreground)]">
                ORCA combines official-source advisories and numerical model evidence for research and education.
              </DialogPrimitive.Description>
            </div>
            <DialogPrimitive.Close asChild><Button variant="ghost" size="icon" aria-label="Close information"><X aria-hidden="true" /></Button></DialogPrimitive.Close>
          </div>
          <p className="mt-5">It is not certified navigation advice. Route hazards, geofences, and official meteorological and maritime warnings are not fully integrated.</p>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
