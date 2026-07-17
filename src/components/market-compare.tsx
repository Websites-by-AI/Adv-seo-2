"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Loader2,
  Crown,
  Eye,
  EyeOff,
  Crosshair,
  FileText,
  Radar,
  ArrowRight,
  CircleAlert,
  BadgeCheck,
  Building2,
  Globe,
  Trophy,
  Percent,
  Sparkles,
  History,
  Satellite,
} from "lucide-react";
import { cn, faNum } from "@/lib/utils";
import type { SerpEntry } from "@/db/schema";
import { ProposalDrawer } from "./proposal-drawer";
import { Button, Chip, SiteFooter, SiteHeader, Stat } from "./ui";

interface MatchItem {
  companyId: number;
  name: string;
  website: string | null;
  googleRank: number | null;
  position: number | null;
  hasProposal: boolean;
  status: string;
}

interface Comparison {
  scan: {
    id: number;
    keyword: string;
    mode: string;
    engine: string;
    results: SerpEntry[];
    createdAt: string;
  };
  present: MatchItem[];
  absent: MatchItem[];
  summary: {
    exhibitorsTotal: number;
    visibleInTop10: number;
    invisible: number;
    visibilityRate: number;
    outsidersInTop10: number;
  };
}

interface HistoryItem {
  id: number;
  keyword: string;
  mode: string;
  engine: string;
  createdAt: string;
}

const MEDALS = ["text-amber-300", "text-zinc-300", "text-amber-600"];

export function MarketCompare() {
  const [keyword, setKeyword] = useState("درب و پنجره یوپی‌وی‌سی تهران");
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [scanning, setScanning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drawerId, setDrawerId] = useState<number | null>(null);
  const [prepIds, setPrepIds] = useState<Set<number>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    const res = await fetch("/api/serp", { cache: "no-store" });
    if (res.ok) {
      const d = await res.json();
      setComparison(d.comparison);
      setHistory(d.history ?? []);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const scan = async (kw?: string) => {
    const k = (kw ?? keyword).trim();
    if (!k) return;
    setScanning(true);
    setError(null);
    try {
      const res = await fetch("/api/serp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keyword: k }),
      });
      const d = await res.json();
      if (!res.ok) {
        setError(d.error ?? "خطا در اسکن");
        return;
      }
      setComparison(d.comparison);
      load();
    } catch {
      setError("خطای ارتباط با سرور");
    } finally {
      setScanning(false);
    }
  };

  /** Make sure pipeline ran, then open the proposal. */
  const openProposal = async (m: MatchItem) => {
    if (!m.hasProposal) {
      setPrepIds((s) => new Set(s).add(m.companyId));
      try {
        await fetch(`/api/companies/${m.companyId}/pipeline`, { method: "POST" });
      } finally {
        setPrepIds((s) => {
          const n = new Set(s);
          n.delete(m.companyId);
          return n;
        });
      }
    }
    setDrawerId(m.companyId);
  };

  const allMatches = comparison
    ? [...comparison.present, ...comparison.absent].sort((a, b) => {
        const pa = a.position ?? 999 + (a.googleRank ?? 999);
        const pb = b.position ?? 999 + (b.googleRank ?? 999);
        return pa - pb;
      })
    : [];

  return (
    <div className="relative mx-auto min-h-screen max-w-7xl px-4 pb-24 sm:px-6">
      <div className="grid-bg pointer-events-none absolute inset-x-0 top-0 h-[520px]" />

      {/* Header */}
      <div className="sticky top-0 z-40 -mx-4 sm:-mx-6">
        <SiteHeader
          tone="amber"
          title="نبرد صفحه اول گوگل"
          subtitle="مقایسه ۱۰ شرکت برتر گوگل با شرکت‌های نمایشگاهی شما"
          actions={
            <Button variant="ghost" href="/" icon={<ArrowRight className="h-4 w-4" />}>
              بازگشت به داشبورد
            </Button>
          }
        />
      </div>

      {/* Scan bar */}
      <section className="relative z-10 mt-8">
        <div className="glass rounded-3xl p-5 sm:p-6">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-600" />
              <input
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && scan()}
                placeholder="کلمه کلیدی کسب‌وکار نمایشگاه — مثلاً: درب و پنجره یوپی‌وی‌سی تهران"
                className="w-full rounded-2xl border border-white/10 bg-black/30 py-4 pr-12 pl-4 text-sm font-bold placeholder:text-zinc-600 focus:border-amber-400/50 focus:outline-none focus:ring-2 focus:ring-amber-400/20"
              />
            </div>
            <Button
              variant="amber"
              size="lg"
              loading={scanning}
              icon={<Satellite className="h-4 w-4" />}
              onClick={() => scan()}
              className="rounded-2xl"
            >
              {scanning ? "در حال اسکن گوگل…" : "اسکن صفحه اول گوگل"}
            </Button>
          </div>
          {error && (
            <p className="mt-3 flex items-center gap-2 text-xs font-bold text-rose-300">
              <CircleAlert className="h-4 w-4" /> {error}
            </p>
          )}
          {history.length > 0 && (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="flex items-center gap-1 text-[10px] font-bold text-zinc-600">
                <History className="h-3 w-3" /> اسکن‌های اخیر:
              </span>
              {history.map((h) => (
                <Chip
                  key={h.id}
                  tone="amber"
                  onClick={() => {
                    setKeyword(h.keyword);
                    scan(h.keyword);
                  }}
                  className="px-3 py-1.5 text-[10px]"
                >
                  {h.keyword}
                  {h.mode === "simulated" && " (برآوردی)"}
                </Chip>
              ))}
            </div>
          )}
        </div>

        {/* Summary strip */}
        {comparison && (
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4"
          >
            <Stat
              icon={Percent}
              label="نرخ دیده‌شدن نمایشگاهی‌ها"
              value={`٪${faNum(comparison.summary.visibilityRate)}`}
              tone={comparison.summary.visibilityRate < 40 ? "text-rose-300" : "text-emerald-300"}
            />
            <Stat
              icon={Eye}
              label="حاضر در صفحه اول"
              value={comparison.summary.visibleInTop10}
              tone="text-emerald-300"
              delay={0.06}
            />
            <Stat
              icon={EyeOff}
              label="غایب (لید فروش سئو)"
              value={comparison.summary.invisible}
              tone="text-amber-300"
              delay={0.12}
            />
            <Stat
              icon={Crown}
              label="رقیب خارج از لیست در تاپ ۱۰"
              value={comparison.summary.outsidersInTop10}
              tone="text-sky-300"
              delay={0.18}
            />
          </motion.div>
        )}
      </section>

      {/* Comparison grid */}
      <section className="relative z-10 mt-6">
        {loading ? (
          <div className="flex justify-center py-24">
            <Loader2 className="h-8 w-8 animate-spin text-amber-400" />
          </div>
        ) : !comparison ? (
          <div className="glass flex flex-col items-center gap-4 rounded-3xl px-6 py-16 text-center">
            <span className="grid h-16 w-16 place-items-center rounded-2xl bg-amber-400/10 ring-1 ring-amber-400/30">
              <Satellite className="h-7 w-7 text-amber-300" />
            </span>
            <h3 className="text-lg font-extrabold">هنوز صفحه اول گوگل اسکن نشده</h3>
            <p className="max-w-md text-sm leading-7 text-zinc-500">
              کلمه کلیدی حوزه نمایشگاه را وارد کنید تا ۱۰ شرکت صفحه اول گوگل استخراج و با لیست
              شرکت‌های نمایشگاهی شما مقایسه شود. غایبان = مشتریان بالقوه فروش سئو.
            </p>
          </div>
        ) : (
          <div className="grid gap-5 lg:grid-cols-2">
            {/* ------ Google Top 10 ------ */}
            <div className="glass rounded-3xl p-5 sm:p-6">
              <div className="flex items-center justify-between gap-3 border-b border-white/8 pb-4">
                <h2 className="flex items-center gap-2 text-sm font-black">
                  <Trophy className="h-4 w-4 text-amber-300" />
                  ۱۰ شرکت سلطان صفحه اول گوگل
                </h2>
                <span
                  className={cn(
                    "rounded-full px-3 py-1 text-[10px] font-black ring-1",
                    comparison.scan.mode === "live"
                      ? "bg-emerald-400/10 text-emerald-300 ring-emerald-400/30"
                      : "bg-amber-400/10 text-amber-300 ring-amber-400/30",
                  )}
                >
                  {comparison.scan.mode === "live"
                    ? `داده زنده — ${comparison.scan.engine}`
                    : "داده برآوردی"}
                </span>
              </div>
              <p className="mt-3 text-[11px] leading-6 text-zinc-500">
                کلمه کلیدی: <span className="font-black text-amber-300">«{comparison.scan.keyword}»</span>
              </p>
              <div className="mt-4 space-y-2">
                {comparison.scan.results.map((r, i) => (
                  <motion.div
                    key={r.position}
                    initial={{ opacity: 0, x: -14 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.04 }}
                    className={cn(
                      "flex items-center gap-3 rounded-2xl px-4 py-3 ring-1 transition",
                      r.matchedCompanyId
                        ? "bg-emerald-400/8 ring-emerald-400/25"
                        : "bg-white/[0.03] ring-white/5 hover:ring-white/15",
                    )}
                  >
                    <span
                      className={cn(
                        "grid h-9 w-9 shrink-0 place-items-center rounded-xl text-sm font-black",
                        r.position <= 3
                          ? "bg-amber-400/15 ring-1 ring-amber-400/30"
                          : "bg-white/5 ring-1 ring-white/10",
                        MEDALS[r.position - 1] ?? "text-zinc-400",
                      )}
                    >
                      {faNum(r.position)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-extrabold leading-6">{r.title}</p>
                      <a
                        href={r.url}
                        target="_blank"
                        rel="noreferrer"
                        dir="ltr"
                        className="flex items-center gap-1 text-left text-[10px] text-sky-400/80 hover:text-sky-300"
                      >
                        <Globe className="h-3 w-3 shrink-0" />
                        <span className="truncate">{r.domain}</span>
                      </a>
                    </div>
                    {r.matchedCompanyId ? (
                      <span className="flex shrink-0 items-center gap-1 rounded-full bg-emerald-400/15 px-2.5 py-1 text-[9px] font-black text-emerald-300 ring-1 ring-emerald-400/30">
                        <BadgeCheck className="h-3 w-3" />
                        از لیست شماست
                      </span>
                    ) : (
                      <span className="shrink-0 rounded-full bg-sky-400/10 px-2.5 py-1 text-[9px] font-black text-sky-300 ring-1 ring-sky-400/25">
                        رقیب خارج از لیست
                      </span>
                    )}
                  </motion.div>
                ))}
              </div>
            </div>

            {/* ------ Your exhibitors ------ */}
            <div className="glass rounded-3xl p-5 sm:p-6">
              <div className="flex items-center justify-between gap-3 border-b border-white/8 pb-4">
                <h2 className="flex items-center gap-2 text-sm font-black">
                  <Building2 className="h-4 w-4 text-emerald-300" />
                  شرکت‌های نمایشگاه شما
                </h2>
                <span className="rounded-full bg-white/5 px-3 py-1 text-[10px] font-black text-zinc-400 ring-1 ring-white/10">
                  {faNum(comparison.summary.exhibitorsTotal)} شرکت
                </span>
              </div>
              <p className="mt-3 text-[11px] leading-6 text-zinc-500">
                هر شرکت سبز یعنی در صفحه اول دیده می‌شود؛ هر شرکت کهربایی یک{" "}
                <span className="font-black text-amber-300">لید داغ برای فروش سئو</span> است.
              </p>
              <div className="mt-4 max-h-[640px] space-y-2 overflow-y-auto pl-1">
                {allMatches.map((m, i) => {
                  const visible = m.position !== null;
                  const prepping = prepIds.has(m.companyId);
                  return (
                    <motion.div
                      key={m.companyId}
                      initial={{ opacity: 0, x: 14 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.03 }}
                      className={cn(
                        "flex items-center gap-3 rounded-2xl px-4 py-3 ring-1",
                        visible
                          ? "bg-emerald-400/8 ring-emerald-400/25"
                          : "bg-amber-400/[0.06] ring-amber-400/20",
                      )}
                    >
                      <span
                        className={cn(
                          "grid h-9 w-9 shrink-0 place-items-center rounded-xl ring-1",
                          visible
                            ? "bg-emerald-400/15 text-emerald-300 ring-emerald-400/30"
                            : "bg-amber-400/15 text-amber-300 ring-amber-400/30",
                        )}
                      >
                        {visible ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-extrabold leading-6">{m.name}</p>
                        <p className="text-[10px] font-bold text-zinc-500">
                          {visible
                            ? `صفحه اول — رتبه ${faNum(m.position!)}`
                            : comparison.scan.mode === "live"
                              ? "در اسکن زنده صفحه اول نیامد"
                              : m.googleRank
                                ? `خارج از صفحه اول — رتبه ${faNum(m.googleRank)}`
                                : "در گوگل دیده نمی‌شود"}
                        </p>
                      </div>
                      {!visible && (
                        <button
                          onClick={() => openProposal(m)}
                          disabled={prepping}
                          className="flex shrink-0 items-center gap-1.5 rounded-xl bg-emerald-500 px-3.5 py-2 text-[10px] font-black text-emerald-950 shadow-lg shadow-emerald-500/25 transition hover:bg-emerald-400 disabled:opacity-50"
                        >
                          {prepping ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : m.hasProposal ? (
                            <FileText className="h-3 w-3" />
                          ) : (
                            <Crosshair className="h-3 w-3" />
                          )}
                          {prepping ? "در حال صدور…" : m.hasProposal ? "پیشنهادنامه" : "صدور پیشنهاد سئو"}
                        </button>
                      )}
                      {visible && (
                        <span className="flex shrink-0 items-center gap-1 rounded-full bg-emerald-400/15 px-2.5 py-1 text-[9px] font-black text-emerald-300 ring-1 ring-emerald-400/30">
                          <BadgeCheck className="h-3 w-3" />
                          فروخته شده
                        </span>
                      )}
                    </motion.div>
                  );
                })}
                {allMatches.length === 0 && (
                  <p className="py-8 text-center text-xs text-zinc-500">
                    لیست نمایشگاه خالی است — از داشبورد، لیست را وارد کنید.
                  </p>
                )}
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Insight strip */}
      {comparison && (
        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className="relative z-10 mt-6 overflow-hidden rounded-3xl border border-amber-400/20 bg-gradient-to-l from-amber-400/10 via-transparent to-emerald-400/10 p-6 sm:p-8"
        >
          <div className="flex flex-wrap items-center gap-4">
            <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-amber-400/15 ring-1 ring-amber-400/40">
              <Sparkles className="h-5 w-5 text-amber-300" />
            </span>
            <div className="min-w-0 flex-1">
              <h3 className="text-base font-black">
                جمع‌بندی نبرد: {faNum(comparison.summary.invisible)} لید داغ در دست شماست
              </h3>
              <p className="mt-1 text-[12px] leading-6 text-zinc-400">
                از {faNum(comparison.summary.exhibitorsTotal)} شرکت نمایشگاهی، فقط{" "}
                {faNum(comparison.summary.visibleInTop10)} شرکت در صفحه اول گوگل دیده می‌شوند و{" "}
                {faNum(comparison.summary.outsidersInTop10)} جای صفحه اول در دست رقبایی است که حتی در
                نمایشگاه غرفه نداشتند. برای هر غایب، با یک کلیک پیشنهادنامه سئو صادر کنید و قرارداد
                را ببندید.
              </p>
            </div>
            <Button
              href="/"
              icon={<Radar className="h-4 w-4" />}
              className="shrink-0"
            >
              رفتن به داشبورد لیدها
            </Button>
          </div>
        </motion.section>
      )}

      <SiteFooter />

      <ProposalDrawer companyId={drawerId} onClose={() => setDrawerId(null)} />
    </div>
  );
}
