"use client";

import { Printer, ArrowRight } from "lucide-react";

export function PrintActions() {
  return (
    <div className="no-print fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 gap-3">
      <button
        onClick={() => window.print()}
        className="flex items-center gap-2 rounded-2xl bg-emerald-500 px-7 py-4 text-sm font-black text-emerald-950 shadow-2xl shadow-emerald-500/40 transition hover:bg-emerald-400"
      >
        <Printer className="h-4 w-4" />
        چاپ / ذخیره PDF
      </button>
      <button
        onClick={() => window.close()}
        className="flex items-center gap-2 rounded-2xl bg-zinc-800 px-5 py-4 text-sm font-bold text-zinc-200 ring-1 ring-white/10 transition hover:bg-zinc-700"
      >
        <ArrowRight className="h-4 w-4" />
        بازگشت
      </button>
    </div>
  );
}
