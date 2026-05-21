"use client";

import { Zap } from "lucide-react";

export function AppHeader({ title }: { title: string }) {
  return (
    // Only visible on mobile — desktop/tablet use the sidebar for context
    <header className="md:hidden flex items-center h-16 px-6 border-b border-border bg-card shrink-0">
      <div className="flex items-center gap-2">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary">
          <Zap className="w-4 h-4 text-primary-foreground" />
        </div>
        <span className="font-bold text-lg text-foreground tracking-tight">LedgerAI</span>
      </div>
    </header>
  );
}
