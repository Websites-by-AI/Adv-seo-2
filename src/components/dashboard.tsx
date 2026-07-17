"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Play,
  Loader2,
  FileText,
  Globe,
  Phone,
  Search,
  CircleCheck,
  CircleX,
  Sparkles,
  FileInput,
  Trash2,
  Crosshair,
  TrendingUp,
  FileCheck2,
  ActivitySquare,
  Globe2,
  FileSearch,
  Telescope,
  Pencil,
  Check,
  RotateCw,
  Swords,
  Gavel,
} from "lucide-react";
import { cn, copyText, faNum } from "@/lib/utils";
import type { FilterKey, LeadRow, LogEntry, Stats } from "./types";
import { ImportModal } from "./import-modal";
import { ProposalDrawer } from "./proposal-drawer";
import { Badge, Button, Chip, SiteFooter, SiteHeader, Stat } from "./ui";

/* ---------------- Score ring ---------------- */
function ScoreRing({ score, mode }: { score: number; mode: string }) {
  const r = 17;
  const c = 2 * Math.PI * r;
  const color =
    mode !== "live" ? "#fb7185" : score >= 70 ? "#34d399" : score >= 45 ? "#fbbf24" : "#fb7185";
  return (
    <div className="relative h-12 w-12" title={`امتیاز سئو: ${faNum(score)}`}>
      <svg viewBox="0 0 44 44" className="h-12 w-12 -rotate-90">
        <circle cx="22" cy="22" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="4" />
        <circle
          cx="22"
          cy="22"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c - (c * score) / 100}
          className="ring-anim"
        />
      </svg>
      <span className="absolute inset-0 grid place-items-center text-[10px] font-black" style={{ color }}>
        {faNum(score)}
      </span>
    </div>
  );
}

/* ---------------- Main dashboard ---------------- */
export function Dashboard() {
  const [leads, setLeads] = useState<LeadRow[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [searchQ, setSearchQ] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [drawerId, setDrawerId] = useState<number | null>(null);
  const [runningIds, setRunningIds] = useState<Set<number>>(new Set());
  const [automationOn, setAutomationOn] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editWebsite, setEditWebsite] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const queueRef = useRef<number[]>([]);
  const activeRef = useRef(0);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const load = useCallback(async () => {
    const [cRes, lRes] = await Promise.all([
      fetch("/api/companies", { cache: "no-store" }),
      fetch("/api/logs", { cache: "no-store" }),
    ]);
    if (cRes.ok) {
      const d = await cRes.json();
      setLeads(d.companies);
      setStats(d.stats);
    }
    if (lRes.ok) {
      const d = await lRes.json();
      setLogs(d.logs);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /* ---------- pipeline runner ---------- */
  const runOne = useCallback(async (id: number): Promise<boolean> => {
    setRunningIds((s) => new Set(s).add(id));
    try {
      const res = await fetch(`/api/companies/${id}/pipeline`, { method: "POST" });
      const data = await res.json();
      if (res.ok && data.company) {
        setLeads((prev) =>
          prev.map((l) =>
            l.id === id ? { ...data.company, audit: data.audit, proposalId: data.proposalId } : l,
          ),
        );
        return true;
      }
    } catch {
      /* ignore */
    } finally {
      setRunningIds((s) => {
        const n = new Set(s);
        n.delete(id);
        return n;
      });
    }
    return false;
  }, []);

  const drainQueue = useCallback(async () => {
    while (queueRef.current.length > 0) {
      const id = queueRef.current.shift()!;
      activeRef.current++;
      await runOne(id);
      activeRef.current--;
    }
    if (activeRef.current === 0 && queueRef.current.length === 0) {
      setAutomationOn(false);
      load();
      showToast("اتوماسیون کامل شد — لیدها و پیشنهادنامه‌ها به‌روز شدند");
    }
  }, [runOne, load]);

  const startAutomation = useCallback(
    (ids: number[]) => {
      if (ids.length === 0) return;
      queueRef.current = [...ids];
      setAutomationOn(true);
      const workers = Math.min(3, ids.length);
      for (let i = 0; i < workers; i++) drainQueue();
    },
    [drainQueue],
  );

  const pendingIds = leads
    .filter((l) => l.status === "new" || (l.onFirstPage === false && !l.proposalId))
    .map((l) => l.id);

  /* ---------- blind tender (confidential bidding widget) ---------- */
  const createBid = async (id: number) => {
    const res = await fetch("/api/bids", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ companyId: id }),
    });
    const d = await res.json();
    if (res.ok && d.bid) {
      const url = `${window.location.origin}/bid/${d.bid.token}`;
      const ok = await copyText(url);
      showToast(
        d.created
          ? ok
            ? "فراخوان کور ساخته شد — لینک ویجت محرمانه کپی شد؛ برای آژانس‌ها بفرستید"
            : `فراخوان کور ساخته شد — لینک ویجت: ${url}`
          : ok
            ? "فراخوان این لید از قبل موجود است — لینک ویجت کپی شد"
            : `فراخوان موجود است — لینک ویجت: ${url}`,
      );
    }
  };

  /* ---------- website inline edit ---------- */
  const saveWebsite = async (id: number) => {
    await fetch(`/api/companies/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ website: editWebsite }),
    });
    setEditingId(null);
    await load();
    showToast("وب‌سایت ثبت شد — برای ممیزی واقعی، اتوماسیون را روی این شرکت اجرا کنید");
  };

  const clearAll = async () => {
    if (!confirm("همه لیدها و پیشنهادنامه‌ها حذف شوند؟")) return;
    await fetch("/api/companies", { method: "DELETE" });
    await load();
    showToast("دیتابیس پاک شد");
  };

  /* ---------- filtering ---------- */
  const filtered = leads.filter((l) => {
    if (searchQ && !l.name.includes(searchQ)) return false;
    switch (filter) {
      case "leads":
        return l.onFirstPage === false;
      case "first-page":
        return l.onFirstPage === true;
      case "no-site":
        return !l.website;
      case "proposals":
        return l.proposalId !== null;
      default:
        return true;
    }
  });

  const FILTERS: { key: FilterKey; label: string }[] = [
    { key: "all", label: "همه" },
    { key: "leads", label: "لیدها (خارج از صفحه اول)" },
    { key: "first-page", label: "در صفحه اول" },
    { key: "no-site", label: "بدون وب‌سایت" },
    { key: "proposals", label: "پیشنهاد آماده" },
  ];

  return (
    <div className="relative mx-auto min-h-screen max-w-7xl px-4 pb-10 sm:px-6">
      <div className="grid-bg pointer-events-none absolute inset-x-0 top-0 h-[520px]" />

      {/* ---------- Header ---------- */}
      <div className="sticky top-0 z-40 -mx-4 sm:-mx-6">
        <SiteHeader
          title="لیدفِر"
          subtitle="اتوماسیون شکار لید نمایشگاهی و پیشنهاد سئو"
          actions={
            <>
              <Button variant="danger" size="sm" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={clearAll}>
                پاک‌سازی
              </Button>
              <Button variant="ghost" icon={<FileInput className="h-4 w-4" />} onClick={() => setImportOpen(true)}>
                واردسازی لیست
              </Button>
              <Button
                icon={<Play className="h-4 w-4" />}
                loading={automationOn}
                disabled={automationOn || pendingIds.length === 0}
                onClick={() => startAutomation(pendingIds)}
              >
                اجرای اتوماسیون{pendingIds.length > 0 && ` (${faNum(pendingIds.length)})`}
              </Button>
            </>
          }
        />
      </div>

      {/* ---------- Hero ---------- */}
      <section className="relative z-10 pt-10 pb-8 text-center">
        <motion.p
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-xs font-bold tracking-wide text-emerald-400"
        >
          از لیست نمایشگاه تا قرارداد سئو — تمام‌خودکار
        </motion.p>
        <motion.h2
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.08 }}
          className="shimmer-text mx-auto mt-3 max-w-3xl text-3xl font-black leading-[1.35] sm:text-5xl sm:leading-[1.3]"
        >
          شرکت‌هایی که در صفحه اول گوگل نیستند را شکار کن
        </motion.h2>
        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.16 }}
          className="mx-auto mt-4 max-w-2xl text-sm leading-8 text-zinc-400"
        >
          لیست شرکت‌کنندگان نمایشگاه را وارد کنید؛ لیدفِر به‌صورت خودکار حضور هر شرکت در گوگل را بررسی
          می‌کند، وب‌سایتشان را ممیزی می‌کند و برای هرکدام که خارج از صفحه اول هستند یک پیشنهادنامه
          آماده سئو برای رسیدن به تاپ ۱۰ گوگل تولید می‌کند.
        </motion.p>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.24 }}
          className="mt-7 flex flex-wrap items-center justify-center gap-3 text-[11px] font-bold text-zinc-400"
        >
          {[
            { icon: FileInput, t: "۱. واردسازی لیست نمایشگاه" },
            { icon: Crosshair, t: "۲. بررسی رتبه گوگل" },
            { icon: FileSearch, t: "۳. ممیزی وب‌سایت" },
            { icon: FileCheck2, t: "۴. صدور پیشنهادنامه" },
          ].map((s, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="glass flex items-center gap-1.5 rounded-full px-3.5 py-2">
                <s.icon className="h-3.5 w-3.5 text-emerald-400" />
                {s.t}
              </span>
              {i < 3 && <span className="hidden h-px w-6 bg-gradient-to-l from-emerald-400/50 to-transparent sm:block" />}
            </div>
          ))}
        </motion.div>
      </section>

      {/* ---------- Stats ---------- */}
      {stats && (
        <section className="relative z-10 mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Stat icon={Swords} label="کل شرکت‌ها" value={stats.total} tone="text-zinc-200" />
          <Stat icon={Crosshair} label="لید شکارشده" value={stats.leads} tone="text-emerald-300" delay={0.05} />
          <Stat icon={CircleCheck} label="در صفحه اول" value={stats.onFirstPage} tone="text-sky-300" delay={0.1} />
          <Stat icon={Globe2} label="بدون وب‌سایت" value={stats.noWebsite} tone="text-amber-300" delay={0.15} />
          <Stat icon={FileCheck2} label="پیشنهاد آماده" value={stats.proposalsReady} tone="text-emerald-300" delay={0.2} />
          <Stat icon={TrendingUp} label="میانگین امتیاز سایت" value={stats.avgScore ?? 0} tone="text-rose-300" delay={0.25} />
        </section>
      )}

      <div className="relative z-10 mt-10 grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* ---------- Leads ---------- */}
        <section>
          {/* Toolbar */}
          <div className="flex flex-wrap items-center gap-2">
            {FILTERS.map((f) => (
              <Chip key={f.key} active={filter === f.key} onClick={() => setFilter(f.key)}>
                {f.label}
              </Chip>
            ))}
            <div className="relative ms-auto">
              <Search className="absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-600" />
              <input
                value={searchQ}
                onChange={(e) => setSearchQ(e.target.value)}
                placeholder="جستجوی شرکت…"
                className="w-44 rounded-full border border-white/10 bg-black/30 py-2 pr-9 pl-3 text-xs placeholder:text-zinc-600 focus:border-emerald-400/40 focus:outline-none"
              />
            </div>
          </div>

          {/* List */}
          <div className="mt-4 space-y-3">
            <AnimatePresence mode="popLayout">
              {filtered.map((lead) => {
                const running = runningIds.has(lead.id);
                const isLead = lead.onFirstPage === false;
                return (
                  <motion.article
                    key={lead.id}
                    layout
                    initial={{ opacity: 0, y: 14 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.97 }}
                    transition={{ type: "spring", stiffness: 320, damping: 30 }}
                    className={cn(
                      "glass glass-hover relative overflow-hidden rounded-2xl p-4 sm:p-5",
                      isLead && "border-emerald-400/20",
                    )}
                  >
                    {isLead && (
                      <span className="absolute inset-y-0 right-0 w-1 bg-gradient-to-b from-emerald-400 to-amber-400" />
                    )}
                    <div className="flex flex-wrap items-center gap-4">
                      {/* Score / status */}
                      <div className="shrink-0">
                        {lead.audit ? (
                          <ScoreRing score={lead.audit.score} mode={lead.audit.mode} />
                        ) : (
                          <div className="grid h-12 w-12 place-items-center rounded-full bg-white/5 ring-1 ring-white/10">
                            {running ? (
                              <Loader2 className="h-5 w-5 animate-spin text-emerald-400" />
                            ) : (
                              <Telescope className="h-5 w-5 text-zinc-600" />
                            )}
                          </div>
                        )}
                      </div>

                      {/* Identity */}
                      <div className="min-w-0 flex-1">
                        <h3 className="truncate text-sm font-extrabold sm:text-base">
                          {lead.name}
                        </h3>
                        <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-zinc-500">
                          {lead.phone && (
                            <span className="flex items-center gap-1" dir="ltr">
                              <Phone className="h-3 w-3" />
                              {lead.phone}
                            </span>
                          )}
                          {lead.website ? (
                            <a
                              href={lead.website}
                              target="_blank"
                              rel="noreferrer"
                              className="flex items-center gap-1 text-sky-400/90 hover:text-sky-300"
                              dir="ltr"
                            >
                              <Globe className="h-3 w-3" />
                              {lead.website.replace(/^https?:\/\//, "").slice(0, 32)}
                            </a>
                          ) : editingId === lead.id ? (
                            <span className="flex items-center gap-1">
                              <input
                                value={editWebsite}
                                onChange={(e) => setEditWebsite(e.target.value)}
                                dir="ltr"
                                placeholder="company.ir"
                                className="w-36 rounded-lg border border-emerald-400/40 bg-black/40 px-2 py-1 text-left text-[11px] focus:outline-none"
                                autoFocus
                                onKeyDown={(e) => e.key === "Enter" && saveWebsite(lead.id)}
                              />
                              <button
                                onClick={() => saveWebsite(lead.id)}
                                className="rounded-md bg-emerald-500/20 p-1 text-emerald-300 hover:bg-emerald-500/30"
                              >
                                <Check className="h-3 w-3" />
                              </button>
                            </span>
                          ) : (
                            <button
                              onClick={() => {
                                setEditingId(lead.id);
                                setEditWebsite("");
                              }}
                              className="flex items-center gap-1 rounded-md bg-amber-400/10 px-2 py-0.5 text-amber-300 ring-1 ring-amber-400/25 hover:bg-amber-400/20"
                            >
                              <Pencil className="h-3 w-3" />
                              وب‌سایت ندارد — افزودن
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Rank badge */}
                      <div className="flex shrink-0 flex-col items-end gap-1.5">
                        {lead.googleRank !== null ? (
                          lead.onFirstPage ? (
                            <Badge tone="sky" icon={<CircleCheck className="h-3.5 w-3.5" />}>
                              صفحه اول — رتبه {faNum(lead.googleRank)}
                            </Badge>
                          ) : (
                            <Badge tone="emerald" icon={<Crosshair className="h-3.5 w-3.5" />}>
                              لید — رتبه {faNum(lead.googleRank)}
                              {lead.rankMode === "simulated" && " (برآورد)"}
                            </Badge>
                          )
                        ) : (
                          <Badge tone="zinc">بررسی نشده</Badge>
                        )}
                        {lead.audit?.mode === "no-site" && (
                          <span className="flex items-center gap-1 text-[10px] font-bold text-amber-300">
                            <CircleX className="h-3 w-3" />
                            بدون وب‌سایت — فرصت طلایی
                          </span>
                        )}
                      </div>

                      {/* Actions */}
                      <div className="flex shrink-0 items-center gap-2">
                        {isLead && (
                          <button
                            onClick={() => createBid(lead.id)}
                            title="صدور فراخوان قیمت‌گذاری محرمانه برای آژانس‌های سئو"
                            className="grid h-10 w-10 place-items-center rounded-xl bg-amber-400/10 ring-1 ring-amber-400/30 transition hover:bg-amber-400/20"
                          >
                            <Gavel className="h-4 w-4 text-amber-300" />
                          </button>
                        )}
                        <button
                          onClick={() => runOne(lead.id)}
                          disabled={running}
                          title="اجرا/به‌روزرسانی تحلیل"
                          className="grid h-10 w-10 place-items-center rounded-xl bg-white/5 ring-1 ring-white/10 transition hover:bg-emerald-400/15 hover:ring-emerald-400/40 disabled:opacity-40"
                        >
                          {running ? (
                            <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
                          ) : lead.status === "new" ? (
                            <Play className="h-4 w-4 text-emerald-300" />
                          ) : (
                            <RotateCw className="h-4 w-4 text-zinc-400" />
                          )}
                        </button>
                        {lead.proposalId && (
                          <Button size="sm" icon={<FileText className="h-3.5 w-3.5" />} onClick={() => setDrawerId(lead.id)}>
                            مشاهده پیشنهادنامه
                          </Button>
                        )}
                      </div>
                    </div>

                    {/* Audit issues preview */}
                    {lead.audit && lead.audit.issues.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5 border-t border-white/5 pt-3">
                        {lead.audit.issues.slice(0, 3).map((iss, i) => (
                          <span
                            key={i}
                            className="rounded-full bg-rose-400/8 px-2.5 py-1 text-[10px] font-bold text-rose-200/80 ring-1 ring-rose-400/15"
                          >
                            {iss}
                          </span>
                        ))}
                        {lead.audit.issues.length > 3 && (
                          <span className="rounded-full bg-white/5 px-2.5 py-1 text-[10px] font-bold text-zinc-500">
                            +{faNum(lead.audit.issues.length - 3)} مشکل دیگر
                          </span>
                        )}
                      </div>
                    )}
                  </motion.article>
                );
              })}
            </AnimatePresence>

            {/* Empty state */}
            {filtered.length === 0 && (
              <motion.div
                initial={{ opacity: 0, scale: 0.97 }}
                animate={{ opacity: 1, scale: 1 }}
                className="glass flex flex-col items-center gap-4 rounded-3xl px-6 py-16 text-center"
              >
                <span className="grid h-16 w-16 place-items-center rounded-2xl bg-emerald-400/10 ring-1 ring-emerald-400/30">
                  <Telescope className="h-7 w-7 text-emerald-300" />
                </span>
                <h3 className="text-lg font-extrabold">
                  {leads.length === 0 ? "هنوز لیستی وارد نکرده‌اید" : "موردی با این فیلتر پیدا نشد"}
                </h3>
                <p className="max-w-md text-sm leading-7 text-zinc-500">
                  {leads.length === 0
                    ? "لیست شرکت‌های نمایشگاه (مثل صفحه نمایشگاه درب و پنجره تهران در iranadfair) را وارد کنید تا اتوماسیون شکار لید آغاز شود."
                    : "فیلتر یا متن جستجو را تغییر دهید."}
                </p>
                {leads.length === 0 && (
                  <Button size="lg" icon={<Sparkles className="h-4 w-4" />} onClick={() => setImportOpen(true)}>
                    واردسازی اولین لیست
                  </Button>
                )}
              </motion.div>
            )}
          </div>
        </section>

        {/* ---------- Activity log ---------- */}
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="glass rounded-2xl p-5">
            <h3 className="flex items-center gap-2 text-sm font-extrabold">
              <span className="relative flex h-2 w-2">
                <span
                  className={cn(
                    "absolute inline-flex h-full w-full rounded-full opacity-75",
                    automationOn ? "animate-ping bg-emerald-400" : "bg-zinc-600",
                  )}
                />
                <span
                  className={cn(
                    "relative inline-flex h-2 w-2 rounded-full",
                    automationOn ? "bg-emerald-400" : "bg-zinc-600",
                  )}
                />
              </span>
              رویدادهای اتوماسیون
              {automationOn && (
                <span className="text-[10px] font-bold text-emerald-400">در حال اجرا…</span>
              )}
            </h3>
            <div className="mt-4 max-h-[480px] space-y-2 overflow-y-auto pl-1">
              {logs.length === 0 && (
                <p className="text-xs leading-6 text-zinc-600">
                  هنوز رویدادی ثبت نشده است. با واردسازی لیست و اجرای اتوماسیون، اینجا زنده به‌روز می‌شود.
                </p>
              )}
              <AnimatePresence initial={false}>
                {logs.map((log) => (
                  <motion.div
                    key={log.id}
                    initial={{ opacity: 0, x: 12 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="rounded-xl bg-white/[0.03] px-3 py-2.5 text-[11px] leading-6 ring-1 ring-white/5"
                  >
                    <span
                      className={cn(
                        "ml-1 inline-block h-1.5 w-1.5 rounded-full align-middle",
                        log.level === "success"
                          ? "bg-emerald-400"
                          : log.level === "warn"
                            ? "bg-amber-400"
                            : log.level === "error"
                              ? "bg-rose-400"
                              : "bg-sky-400",
                      )}
                    />
                    <span className="text-zinc-300">{log.message}</span>
                    <span className="mt-1 block text-[9px] text-zinc-600">
                      {new Date(log.createdAt).toLocaleTimeString("fa-IR")}
                    </span>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </div>

          <div className="glass mt-4 rounded-2xl p-5">
            <h3 className="flex items-center gap-2 text-sm font-extrabold">
              <ActivitySquare className="h-4 w-4 text-emerald-400" />
              لیدفِر چه می‌کند؟
            </h3>
            <ul className="mt-3 space-y-2.5 text-[11px] leading-6 text-zinc-400">
              <li>• استخراج خودکار نام و تلفن شرکت‌ها از صفحات لیست نمایشگاه</li>
              <li>• بررسی حضور هر شرکت در نتایج گوگل و تشخیص غایبان صفحه اول</li>
              <li>• ممیزی فنی وب‌سایت: تایتل، متا، H1، سرعت، اسکیما و موبایل</li>
              <li>• تولید پیشنهادنامه فارسی آماده ارسال برای رسیدن به تاپ ۱۰ گوگل</li>
            </ul>
          </div>
        </aside>
      </div>

      <SiteFooter />

      {/* ---------- Toast ---------- */}
      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-2xl bg-emerald-400 px-6 py-3.5 text-sm font-black text-emerald-950 shadow-2xl shadow-emerald-500/40"
          >
            {toast}
          </motion.div>
        )}
      </AnimatePresence>

      <ImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onDone={(msg) => {
          showToast(msg);
          load();
        }}
      />
      <ProposalDrawer companyId={drawerId} onClose={() => setDrawerId(null)} />
    </div>
  );
}
