"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Gavel,
  Copy,
  Loader2,
  Lock,
  Unlock,
  Building2,
  Banknote,
  CalendarClock,
  CircleCheck,
  ExternalLink,
  Handshake,
  Search,
  Gauge,
  Factory,
} from "lucide-react";
import type { BidRequest, BidSnapshot, Quote } from "@/db/schema";
import { cn, copyText, faNum } from "@/lib/utils";
import { Badge, Button, SiteFooter, SiteHeader, Stat } from "./ui";

interface BidItem extends BidRequest {
  companyName: string;
  companyPhone: string | null;
  companyWebsite: string | null;
  quotes: Quote[];
}

export function BidsMarket() {
  const [bids, setBids] = useState<BidItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [awarding, setAwarding] = useState<number | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4500);
  };

  const load = useCallback(async () => {
    const res = await fetch("/api/bids", { cache: "no-store" });
    if (res.ok) {
      const d = await res.json();
      setBids(d.bids);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const copyWidgetLink = async (token: string) => {
    const url = `${window.location.origin}/bid/${token}`;
    const ok = await copyText(url);
    if (ok) {
      setCopied(token);
      setTimeout(() => setCopied(null), 2000);
      showToast("لینک ویجت فراخوان کپی شد — برای آژانس‌های سئو ارسال کنید");
    } else {
      showToast(`لینک ویجت: ${url}`);
    }
  };

  const award = async (bid: BidItem, quote: Quote) => {
    const commission = Math.round((quote.amountMin * bid.commissionPercent) / 100);
    if (
      !confirm(
        `تسویه پورسانت ${faNum(bid.commissionPercent)}٪ (${faNum(commission)} تومان به‌ازای حداقل قرارداد) و واگذاری اطلاعات کامل «${bid.companyName}» به «${quote.agencyName}»؟`,
      )
    )
      return;
    setAwarding(quote.id);
    try {
      const res = await fetch(`/api/bids/${bid.token}/award`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ quoteId: quote.id }),
      });
      const d = await res.json();
      if (res.ok) {
        showToast(`تسویه شد — لید به «${d.winner}» سپرده شد`);
        load();
      }
    } finally {
      setAwarding(null);
    }
  };

  const open = bids.filter((b) => b.status === "open").length;
  const revealed = bids.filter((b) => b.status === "revealed").length;
  const totalQuotes = bids.reduce((s, b) => s + b.quotes.length, 0);

  return (
    <div className="relative mx-auto min-h-screen max-w-7xl px-4 pb-10 sm:px-6">
      <div className="grid-bg pointer-events-none absolute inset-x-0 top-0 h-[520px]" />

      <div className="sticky top-0 z-40 -mx-4 sm:-mx-6">
        <SiteHeader
          tone="amber"
          title="بازار مناقصه کور سئو"
          subtitle="فراخوان محرمانه برای آژانس‌های سئو ایران — واگذاری لید پس از پورسانت"
          actions={<Button variant="ghost" href="/">داشبورد لیدها</Button>}
        />
      </div>

      {/* Stats */}
      <section className="relative z-10 mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat icon={Gavel} label="فراخوان‌های باز" value={open} tone="text-amber-300" />
        <Stat icon={Banknote} label="قیمت‌های ثبت‌شده" value={totalQuotes} tone="text-emerald-300" delay={0.06} />
        <Stat icon={Unlock} label="لیدهای واگذارشده" value={revealed} tone="text-sky-300" delay={0.12} />
        <Stat icon={Handshake} label="پورسانت پلتفرم" value={15} suffix="٪" tone="text-zinc-200" delay={0.18} />
      </section>

      {/* How it works */}
      <section className="relative z-10 mt-6 grid gap-3 sm:grid-cols-3">
        {[
          { icon: Lock, t: "۱. فراخوان کور", d: "برای هر لید یک ویجت محرمانه می‌سازید؛ نام، تلفن و سایت شرکت هرگز به آژانس نشان داده نمی‌شود." },
          { icon: Banknote, t: "۲. قیمت‌دهی آژانس‌ها", d: "آژانس‌های سئوی ایران روی محدوده کار (پکیج ۱۰ بخشی) قیمت رقابتی ثبت می‌کنند." },
          { icon: Unlock, t: "۳. تسویه و واگذاری", d: "بهترین قیمت را انتخاب می‌کنید؛ پورسانت ۱۵٪ تسویه می‌شود و اطلاعات کامل لید به برنده سپرده می‌شود." },
        ].map((s, i) => (
          <motion.div
            key={s.t}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.07 }}
            className="glass rounded-2xl p-5"
          >
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-amber-400/10 ring-1 ring-amber-400/30">
              <s.icon className="h-4 w-4 text-amber-300" />
            </span>
            <h3 className="mt-3 text-sm font-black">{s.t}</h3>
            <p className="mt-1.5 text-[11px] leading-6 text-zinc-400">{s.d}</p>
          </motion.div>
        ))}
      </section>

      {/* Bid list */}
      <section className="relative z-10 mt-8 space-y-4">
        {loading ? (
          <div className="flex justify-center py-24">
            <Loader2 className="h-8 w-8 animate-spin text-amber-400" />
          </div>
        ) : bids.length === 0 ? (
          <div className="glass flex flex-col items-center gap-4 rounded-3xl px-6 py-16 text-center">
            <span className="grid h-16 w-16 place-items-center rounded-2xl bg-amber-400/10 ring-1 ring-amber-400/30">
              <Gavel className="h-7 w-7 text-amber-300" />
            </span>
            <h3 className="text-lg font-extrabold">هنوز فراخوانی صادر نشده</h3>
            <p className="max-w-md text-sm leading-7 text-zinc-500">
              از داشبورد، روی آیکون چکش کنار هر لید کلیک کنید تا فراخوان قیمت‌گذاری محرمانه آن ساخته
              و لینک ویجت آن برای آژانس‌ها آماده شود.
            </p>
            <Button variant="amber" href="/">رفتن به داشبورد</Button>
          </div>
        ) : (
          <AnimatePresence mode="popLayout">
            {bids.map((bid) => (
              <motion.article
                key={bid.id}
                layout
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.97 }}
                className={cn(
                  "glass glass-hover rounded-3xl p-5 sm:p-6",
                  bid.status === "revealed" && "border-emerald-400/25",
                )}
              >
                {/* Header row */}
                <div className="flex flex-wrap items-center gap-3">
                  <span
                    className={cn(
                      "grid h-11 w-11 place-items-center rounded-2xl ring-1",
                      bid.status === "revealed"
                        ? "bg-emerald-400/10 text-emerald-300 ring-emerald-400/30"
                        : "bg-amber-400/10 text-amber-300 ring-amber-400/30",
                    )}
                  >
                    {bid.status === "revealed" ? <Unlock className="h-5 w-5" /> : <Lock className="h-5 w-5" />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <h3 className="flex flex-wrap items-center gap-2 text-sm font-black sm:text-base">
                      {bid.alias}
                      <Badge tone="zinc" icon={<Factory className="h-3 w-3" />}>
                        {bid.industry}
                      </Badge>
                    </h3>
                    <p className="mt-1 text-[11px] text-zinc-500">
                      کارفرما (فقط برای شما): <span className="font-black text-zinc-300">{bid.companyName}</span>
                      {" — در ویجت محرمانه است"}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {bid.status === "open" ? (
                      <Badge tone="amber">در حال قیمت‌دهی — {faNum(bid.quotes.length)} قیمت</Badge>
                    ) : (
                      <Badge tone="emerald" icon={<CircleCheck className="h-3.5 w-3.5" />}>
                        تسویه و واگذارشده
                      </Badge>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={copied === bid.token ? <CircleCheck className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                      onClick={() => copyWidgetLink(bid.token)}
                    >
                      {copied === bid.token ? "کپی شد" : "کپی لینک ویجت"}
                    </Button>
                    <Button variant="outline" size="sm" href={`/bid/${bid.token}`} icon={<ExternalLink className="h-3.5 w-3.5" />}>
                      مشاهده ویجت
                    </Button>
                  </div>
                </div>

                {/* Snapshot chips */}
                <div className="mt-4 flex flex-wrap gap-2 text-[10px] font-bold">
                  <span className="flex items-center gap-1 rounded-full bg-white/5 px-3 py-1.5 text-zinc-400 ring-1 ring-white/10">
                    <Search className="h-3 w-3" />
                    رتبه گوگل: {bid.snapshot.googleRank ? faNum(bid.snapshot.googleRank) : "نامرئی"}
                  </span>
                  <span className="flex items-center gap-1 rounded-full bg-white/5 px-3 py-1.5 text-zinc-400 ring-1 ring-white/10">
                    <Gauge className="h-3 w-3" />
                    امتیاز سایت: {bid.snapshot.score !== null ? faNum(bid.snapshot.score) : "—"}
                  </span>
                  <span className="rounded-full bg-white/5 px-3 py-1.5 text-zinc-400 ring-1 ring-white/10">
                    بازه مرجع پکیج: {faNum(bid.snapshot.totalMin)} تا {faNum(bid.snapshot.totalMax)} تومان
                  </span>
                </div>

                {/* Quotes */}
                {bid.quotes.length > 0 && (
                  <div className="mt-4 space-y-2 border-t border-white/8 pt-4">
                    <p className="text-[11px] font-black text-zinc-400">
                      قیمت‌های ثبت‌شده ({faNum(bid.quotes.length)}):
                    </p>
                    {bid.quotes.map((q) => {
                      const won = q.status === "won";
                      return (
                        <div
                          key={q.id}
                          className={cn(
                            "flex flex-wrap items-center gap-3 rounded-2xl px-4 py-3 ring-1",
                            won
                              ? "bg-emerald-400/10 ring-emerald-400/30"
                              : q.status === "rejected"
                                ? "bg-white/[0.02] ring-white/5 opacity-50"
                                : "bg-white/[0.03] ring-white/10",
                          )}
                        >
                          <Building2 className={cn("h-4 w-4 shrink-0", won ? "text-emerald-300" : "text-zinc-500")} />
                          <div className="min-w-0 flex-1">
                            <p className="text-[13px] font-extrabold">{q.agencyName}</p>
                            {q.note && <p className="mt-0.5 text-[10px] text-zinc-500">{q.note}</p>}
                          </div>
                          <span className="flex items-center gap-1 text-[11px] font-black text-amber-300">
                            <Banknote className="h-3.5 w-3.5" />
                            {faNum(q.amountMin)} تا {faNum(q.amountMax)} تومان
                          </span>
                          <span className="flex items-center gap-1 text-[10px] font-bold text-zinc-500">
                            <CalendarClock className="h-3 w-3" />
                            {faNum(q.durationDays)} روز
                          </span>
                          {bid.status === "open" && (
                            <Button
                              size="sm"
                              loading={awarding === q.id}
                              icon={<Handshake className="h-3.5 w-3.5" />}
                              onClick={() => award(bid, q)}
                            >
                              تسویه پورسانت و واگذاری
                            </Button>
                          )}
                          {won && (
                            <Badge tone="emerald" icon={<CircleCheck className="h-3.5 w-3.5" />}>
                              برنده — لید سپرده شد
                            </Badge>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </motion.article>
            ))}
          </AnimatePresence>
        )}
      </section>

      <SiteFooter />

      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-2xl bg-amber-400 px-6 py-3.5 text-sm font-black text-amber-950 shadow-2xl shadow-amber-400/40"
          >
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
