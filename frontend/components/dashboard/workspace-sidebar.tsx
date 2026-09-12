"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { BookOpen, ChevronLeft, Menu, MessageSquareText, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";

const items = [
  { id: "new", label: "New analysis", icon: Plus },
  { id: "conversation", label: "Conversations", icon: MessageSquareText },
  { id: "sources", label: "Sources", icon: BookOpen },
] as const;

export function WorkspaceSidebar({
  collapsed,
  onCollapsedChange,
  mobileOpen,
  onMobileOpenChange,
  onAction,
  conversationActive,
  demoEnabled,
}: {
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  mobileOpen: boolean;
  onMobileOpenChange: (open: boolean) => void;
  onAction: (id: typeof items[number]["id"]) => void;
  conversationActive: boolean;
  demoEnabled: boolean;
}) {
  const navigation = (compact: boolean) => <nav aria-label="ORCA workspace" className="grid gap-2 p-3">
    {items.map((item) => {
      const Icon = item.icon;
      const disabled = false;
      return <button
        key={item.id}
        type="button"
        className={`workspace-nav-item ${item.id === "conversation" && conversationActive ? "workspace-nav-active" : ""}`}
        aria-label={compact ? item.label : undefined}
        title={compact ? item.label : undefined}
        disabled={disabled}
        onClick={() => { onAction(item.id); onMobileOpenChange(false); }}
      >
        <Icon aria-hidden="true" className="size-5 shrink-0" />
        {!compact && <span>{item.label}</span>}
      </button>;
    })}
  </nav>;

  return <>
    <aside className={`workspace-sidebar hidden xl:flex ${collapsed ? "workspace-sidebar-collapsed" : ""}`}>
      <div className="flex min-h-16 items-center gap-3 border-b border-white/10 px-4">
        <div className="orca-mark" aria-hidden="true"><span /></div>
        {!collapsed && <div className="min-w-0"><p className="font-bold tracking-[0.12em]">ORCA</p><p className="text-[0.65rem] text-slate-300">MARINE INTELLIGENCE</p></div>}
      </div>
      {navigation(collapsed)}
      <div className="mt-auto border-t border-white/10 p-3">
        {!collapsed && <p className="mb-3 text-xs leading-5 text-slate-300">Decision support only. Verify authority advisories independently.</p>}
        <Button type="button" variant="ghost" className="w-full text-white hover:bg-white/10" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} onClick={() => onCollapsedChange(!collapsed)}>
          <ChevronLeft aria-hidden="true" className={`size-4 transition-transform ${collapsed ? "rotate-180" : ""}`} />{!collapsed && "Collapse"}
        </Button>
      </div>
    </aside>
    <DialogPrimitive.Root open={mobileOpen} onOpenChange={onMobileOpenChange}>
      <DialogPrimitive.Trigger asChild><Button variant="ghost" size="icon" className="mobile-menu-trigger" aria-label="Open workspace navigation"><Menu aria-hidden="true" /></Button></DialogPrimitive.Trigger>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-slate-950/60 xl:hidden" />
        <DialogPrimitive.Content className="fixed inset-y-0 left-0 z-50 flex w-[min(20rem,88vw)] flex-col bg-[var(--primary)] text-white shadow-2xl focus:outline-none xl:hidden">
          <div className="flex min-h-16 items-center justify-between border-b border-white/10 px-4"><DialogPrimitive.Title className="font-bold">ORCA workspace</DialogPrimitive.Title><DialogPrimitive.Close asChild><Button variant="ghost" size="icon" className="text-white hover:bg-white/10" aria-label="Close workspace navigation"><X aria-hidden="true" /></Button></DialogPrimitive.Close></div>
          <DialogPrimitive.Description className="px-4 pt-3 text-sm text-slate-300">Workspace navigation</DialogPrimitive.Description>
          {navigation(false)}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  </>;
}
