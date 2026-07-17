"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Printer,
  Loader2,
  BadgeCheck,
  Target,
  FileText,
  KeyRound,
  Route,
  AlertTriangle,
  Binoculars,
  Wallet,
  ShieldAlert,
  Banknote,
  Gavel,
} from "lucide-react";
import type { PenaltyItem, PricingItem, ProposalSection } from "@/db/schema";
import { cn, faNum } from "@/lib/utils";

interface FullProposal {
  company: {
    id: number;
    name: string;
    phone: string | null;
    website: string | null;
    googleRank: number | null;
    onFirstPage: boolean | null;
  };
  audit: { score: number; mode: string; issues: string[] } | null;
  proposal: {
    id: number;
    keyword: string;
    grade: string;
    summary: string;
    keywords: string[];
    sections: ProposalSection[];
    pricing: PricingItem[];
    penalties: PenaltyItem[];
    totalMin: number | null;
    totalMax: number | null;
    createdAt: string;
  } | null;
}

const SECTION_ICONS = [Binoculars, AlertTriangle, Route, KeyRound, Target];

function toman(n: number): string {
  return `${faNum(n)} تومان`;
}

export function ProposalDrawer({
  companyId,
  onClose,
}: {
  companyId: number | null;
  onClose: () => void;
}) {
  const [data, setData] = useState<FullProposal | null>(null);
  const [loadedId, setLoadedId] = useState<number | null>(null);

  useEffect(() => {
    if (companyId === null) return;
    let cancelled = false;
    fetch(`/api/companies/${companyId}`)
      .then((r) => r.json())
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setLoadedId(companyId);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  const open = companyId !== null;
  const loading = open && loadedId !== companyId;
  const current = open && loadedId === companyId ? data : null;

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
          <motion.aside
            initial={{ x: "-100%" }}
            animate={{ x: 0 }}
            exit={{ x: "-100%" }}
            transition={{ type: "spring", stiffness: 300, damping: 32 }}
            className="absolute inset-y-0 left-0 w-full max-w-2xl overflow-y-auto border-r border-white/10 bg-[#0a0f14] shadow-2xl"
          >
            {loading || !current ? (
              <div className="flex h-full items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
              </div>
            ) : !current.proposal ? (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-400">
                <FileText className="h-10 w-10" />
                پیشنهادنامه‌ای برای این شرکت هنوز صادر نشده است
                <button onClick={onClose} className="text-emerald-400 underline">
                  بازگشت
                </button>
              </div>
            ) : (
              <div className="p-6 sm:p-10">
                {/* Header */}
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="flex items-center gap-1.5 text-xs font-bold text-emerald-400">
                      <BadgeCheck className="h-4 w-4" />
                      پیشنهادنامه آماده ارسال — اولویت {current.proposal.grade}
                    </p>
                    <h2 className="mt-2 text-2xl font-black leading-snug">
                      پیشنهاد ارتقای رتبه گوگل
                      <br />
                      <span className="text-emerald-300">{current.company.name}</span>
                    </h2>
                  </div>
                  <button
                    onClick={onClose}
                    className="rounded-full p-2 text-zinc-400 transition hover:bg-white/10 hover:text-white"
                    aria-label="بستن"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                {/* Meta chips */}
                <div className="mt-4 flex flex-wrap gap-2 text-xs">
                  {current.company.phone && (
                    <span className="rounded-full bg-white/5 px-3 py-1.5 text-zinc-300 ring-1 ring-white/10" dir="ltr">
                      {current.company.phone}
                    </span>
                  )}
                  <span className="rounded-full bg-white/5 px-3 py-1.5 text-zinc-300 ring-1 ring-white/10">
                    رتبه فعلی: {current.company.googleRank ? faNum(current.company.googleRank) : "—"}
                  </span>
                  {current.audit && (
                    <span className="rounded-full bg-white/5 px-3 py-1.5 text-zinc-300 ring-1 ring-white/10">
                      امتیاز سایت: {faNum(current.audit.score)}/۱۰۰
                    </span>
                  )}
                </div>

                {/* Summary */}
                <div className="glass mt-6 rounded-2xl p-5 text-sm leading-8 text-zinc-200">
                  {current.proposal.summary}
                </div>

                {/* Sections */}
                <div className="mt-8 space-y-8">
                  {current.proposal.sections.map((s, i) => {
                    const Icon = SECTION_ICONS[i % SECTION_ICONS.length];
                    return (
                      <motion.section
                        key={s.heading}
                        initial={{ opacity: 0, y: 16 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: "-40px" }}
                        transition={{ duration: 0.5, delay: i * 0.04 }}
                      >
                        <h3 className="flex items-center gap-2 text-base font-extrabold text-emerald-300">
                          <span className="grid h-8 w-8 place-items-center rounded-xl bg-emerald-400/10 ring-1 ring-emerald-400/30">
                            <Icon className="h-4 w-4" />
                          </span>
                          {s.heading}
                        </h3>
                        <p className="mt-3 text-sm leading-8 text-zinc-300">{s.body}</p>
                        {s.bullets && (
                          <ul className="mt-3 space-y-2">
                            {s.bullets.map((b, j) => (
                              <li
                                key={j}
                                className="flex items-start gap-2 rounded-xl bg-white/[0.03] px-4 py-2.5 text-sm leading-7 text-zinc-300 ring-1 ring-white/5"
                              >
                                <span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                                {b}
                              </li>
                            ))}
                          </ul>
                        )}
                      </motion.section>
                    );
                  })}
                </div>

                {/* -------- 6. Pricing package -------- */}
                {current.proposal.pricing.length > 0 && (
                  <motion.section
                    initial={{ opacity: 0, y: 16 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    className="mt-10"
                  >
                    <h3 className="flex items-center gap-2 text-base font-extrabold text-amber-300">
                      <span className="grid h-8 w-8 place-items-center rounded-xl bg-amber-400/10 ring-1 ring-amber-400/30">
                        <Wallet className="h-4 w-4" />
                      </span>
                      ۶. ساختار پکیج سئو و برآورد شفاف هزینه
                    </h3>
                    <p className="mt-2 text-xs leading-6 text-zinc-500">
                      {faNum(current.proposal.pricing.length)} بخش خدماتی — هر بخش با جزئیات کار و بازه هزینه واقعی بازار (تومان):
                    </p>
                    <div className="mt-4 space-y-2">
                      {current.proposal.pricing.map((p, i) => (
                        <div
                          key={p.title}
                          className="flex items-start gap-3 rounded-2xl bg-white/[0.03] px-4 py-3.5 ring-1 ring-white/5"
                        >
                          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-amber-400/10 text-xs font-black text-amber-300 ring-1 ring-amber-400/25">
                            {faNum(i + 1)}
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="text-[13px] font-extrabold text-zinc-100">{p.title}</p>
                            <p className="mt-1 text-[11px] leading-6 text-zinc-500">{p.details}</p>
                          </div>
                          <div className="shrink-0 text-left">
                            <p className="flex items-center gap-1 text-[11px] font-black text-amber-300">
                              <Banknote className="h-3.5 w-3.5" />
                              {faNum(p.costMin)} تا {faNum(p.costMax)}
                            </p>
                            <p className="mt-1 text-[9px] font-bold text-zinc-600">تومان</p>
                          </div>
                        </div>
                      ))}
                    </div>
                    {/* Total */}
                    <div className="mt-3 flex items-center justify-between rounded-2xl bg-amber-400 px-5 py-4 text-amber-950 shadow-lg shadow-amber-400/25">
                      <span className="text-sm font-black">جمع سرمایه‌گذاری پکیج کامل</span>
                      <span className="text-sm font-black tabular-nums">
                        {faNum(current.proposal.totalMin ?? 0)} تا {faNum(current.proposal.totalMax ?? 0)} تومان
                      </span>
                    </div>
                    <p className="mt-2 text-[10px] leading-5 text-zinc-500">
                      امکان پرداخت اقساطی ۳ ماهه وجود دارد. انتخاب تک‌آیتمی از پکیج نیز ممکن است، اما
                      بیشترین بازگشت سرمایه با اجرای هماهنگ همه بخش‌ها حاصل می‌شود.
                    </p>
                  </motion.section>
                )}

                {/* -------- 7. Google penalty blacklist -------- */}
                {current.proposal.penalties.length > 0 && (
                  <motion.section
                    initial={{ opacity: 0, y: 16 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    className="mt-10"
                  >
                    <h3 className="flex items-center gap-2 text-base font-extrabold text-rose-300">
                      <span className="grid h-8 w-8 place-items-center rounded-xl bg-rose-400/10 ring-1 ring-rose-400/30">
                        <ShieldAlert className="h-4 w-4" />
                      </span>
                      ۷. خط قرمزهای گوگل — کارهایی که هرگز نباید انجام شوند
                    </h3>
                    <p className="mt-2 text-xs leading-6 text-zinc-500">
                      تیم ما فقط سئوی وایت‌هت اجرا می‌کند. روش‌های زیر (سئو کلاه‌سیاه) که متأسفانه بعضی
                      مجریان پیشنهاد می‌دهند، سایت شما را برای همیشه از گوگل حذف می‌کنند:
                    </p>
                    <div className="mt-4 space-y-2">
                      {current.proposal.penalties.map((pen) => (
                        <div
                          key={pen.title}
                          className="flex items-start gap-3 rounded-2xl bg-rose-400/[0.06] px-4 py-3 ring-1 ring-rose-400/15"
                        >
                          <Gavel className="mt-1 h-4 w-4 shrink-0 text-rose-400" />
                          <div>
                            <p className="text-[12px] font-extrabold text-rose-100">{pen.title}</p>
                            <p className="mt-0.5 text-[11px] leading-5 text-rose-300/70">
                              پیامد: {pen.consequence}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div
                      className={cn(
                        "mt-3 rounded-2xl border border-dashed border-emerald-400/30 bg-emerald-400/5 px-4 py-3",
                      )}
                    >
                      <p className="text-[11px] font-bold leading-6 text-emerald-200">
                        تعهد ما: صددرصد وایت‌هت. هر روش پیشنهادی ما منطبق بر دستورالعمل‌های رسمی گوگل
                        است و کاهش رتبه ناشی از پنالتی، مسئولیت اجرایی ماست.
                      </p>
                    </div>
                  </motion.section>
                )}

                {/* Actions */}
                <div className="sticky bottom-0 mt-10 flex gap-3 border-t border-white/10 bg-[#0a0f14]/95 py-4 backdrop-blur">
                  <a
                    href={`/proposal/${current.company.id}`}
                    target="_blank"
                    className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-emerald-500 px-5 py-3.5 text-sm font-extrabold text-emerald-950 shadow-lg shadow-emerald-500/25 transition hover:bg-emerald-400"
                  >
                    <Printer className="h-4 w-4" />
                    نسخه چاپی / PDF
                  </a>
                  <button
                    onClick={onClose}
                    className="rounded-xl border border-white/15 px-5 py-3.5 text-sm font-bold text-zinc-300 transition hover:bg-white/5"
                  >
                    بستن
                  </button>
                </div>
              </div>
            )}
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
