"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Link2,
  Code2,
  ListPlus,
  Sparkles,
  Loader2,
  FileInput,
  CircleAlert,
} from "lucide-react";
import { cn } from "@/lib/utils";

type Tab = "url" | "html" | "manual" | "sample";

const TABS: { key: Tab; label: string; icon: typeof Link2 }[] = [
  { key: "url", label: "آدرس صفحه", icon: Link2 },
  { key: "html", label: "کد HTML", icon: Code2 },
  { key: "manual", label: "ورود دستی", icon: ListPlus },
  { key: "sample", label: "داده نمونه", icon: Sparkles },
];

export function ImportModal({
  open,
  onClose,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  onDone: (msg: string) => void;
}) {
  const [tab, setTab] = useState<Tab>("url");
  const [url, setUrl] = useState("");
  const [html, setHtml] = useState("");
  const [text, setText] = useState("");
  const [exhibitionName, setExhibitionName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: tab,
          url: url || undefined,
          html: html || undefined,
          text: text || undefined,
          exhibitionName: exhibitionName || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? "خطا در واردسازی");
        return;
      }
      onDone(
        `${data.inserted} شرکت جدید وارد شد${data.skipped > 0 ? ` — ${data.skipped} مورد تکراری بود` : ""}`,
      );
      setUrl("");
      setHtml("");
      setText("");
      setExhibitionName("");
      onClose();
    } catch {
      setError("خطای ارتباط با سرور");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.div
            initial={{ y: 40, scale: 0.96, opacity: 0 }}
            animate={{ y: 0, scale: 1, opacity: 1 }}
            exit={{ y: 20, scale: 0.97, opacity: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 26 }}
            className="glass relative w-full max-w-2xl rounded-3xl p-6 sm:p-8 shadow-2xl"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-extrabold flex items-center gap-2">
                  <FileInput className="h-5 w-5 text-emerald-400" />
                  واردسازی لیست نمایشگاه
                </h2>
                <p className="mt-1 text-sm text-zinc-400">
                  لیست شرکت‌کنندگان نمایشگاه را از سایت‌هایی مثل iranadfair وارد کنید
                </p>
              </div>
              <button
                onClick={onClose}
                className="rounded-full p-2 text-zinc-400 hover:bg-white/10 hover:text-white transition"
                aria-label="بستن"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Tabs */}
            <div className="mt-6 grid grid-cols-4 gap-2 rounded-2xl bg-black/30 p-1.5">
              {TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={cn(
                    "relative flex flex-col items-center gap-1 rounded-xl px-2 py-2.5 text-xs font-bold transition",
                    tab === t.key
                      ? "text-emerald-300"
                      : "text-zinc-500 hover:text-zinc-300",
                  )}
                >
                  {tab === t.key && (
                    <motion.span
                      layoutId="tab-pill"
                      className="absolute inset-0 rounded-xl bg-emerald-400/10 ring-1 ring-emerald-400/30"
                      transition={{ type: "spring", stiffness: 400, damping: 32 }}
                    />
                  )}
                  <t.icon className="relative h-4 w-4" />
                  <span className="relative">{t.label}</span>
                </button>
              ))}
            </div>

            <div className="mt-5 space-y-4">
              <input
                value={exhibitionName}
                onChange={(e) => setExhibitionName(e.target.value)}
                placeholder="نام نمایشگاه (اختیاری) — مثلاً: نمایشگاه درب و پنجره تهران ۱۴۰۴"
                className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm placeholder:text-zinc-600 focus:border-emerald-400/50 focus:outline-none focus:ring-2 focus:ring-emerald-400/20"
              />

              {tab === "url" && (
                <div className="space-y-2">
                  <input
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    dir="ltr"
                    placeholder="https://iranadfair.com/ad_category/..."
                    className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-left text-sm placeholder:text-zinc-600 focus:border-emerald-400/50 focus:outline-none focus:ring-2 focus:ring-emerald-400/20"
                  />
                  <p className="text-xs leading-5 text-zinc-500">
                    آدرس صفحه‌ای که لیست شرکت‌های نمایشگاه را نمایش می‌دهد. اگر سرور مقصد دریافت را مسدود کرد، از تب «کد HTML» استفاده کنید (در مرورگر: Ctrl+U سپس کپی کل صفحه).
                  </p>
                </div>
              )}

              {tab === "html" && (
                <textarea
                  value={html}
                  onChange={(e) => setHtml(e.target.value)}
                  dir="ltr"
                  rows={7}
                  placeholder="<html>… سورس کامل صفحه لیست نمایشگاه را اینجا جای‌گذاری کنید …"
                  className="w-full resize-none rounded-xl border border-white/10 bg-black/30 px-4 py-3 font-mono text-left text-xs placeholder:text-zinc-600 focus:border-emerald-400/50 focus:outline-none focus:ring-2 focus:ring-emerald-400/20"
                />
              )}

              {tab === "manual" && (
                <div className="space-y-2">
                  <textarea
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    rows={7}
                    placeholder={"هر خط یک شرکت: نام | تلفن | وب‌سایت\nشرکت پنجره سازان آریا | 09121112233 | aryawindow.ir\nتولیدی یوپی‌وی‌سی الوند | 02144556677"}
                    className="w-full resize-none rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm leading-7 placeholder:text-zinc-600 focus:border-emerald-400/50 focus:outline-none focus:ring-2 focus:ring-emerald-400/20"
                  />
                  <p className="text-xs text-zinc-500">
                    فرمت هر خط: نام شرکت | شماره تماس | وب‌سایت (تلفن و وب‌سایت اختیاری‌اند)
                  </p>
                </div>
              )}

              {tab === "sample" && (
                <div className="rounded-xl border border-dashed border-amber-400/30 bg-amber-400/5 p-4 text-sm leading-7 text-amber-100/80">
                  ۱۴ شرکت نمونه از «لیست شرکت‌کنندگان نمایشگاه درب و پنجره تهران ۱۴۰۴» وارد می‌شود تا فوراً اتوماسیون را امتحان کنید.
                </div>
              )}

              {error && (
                <div className="flex items-start gap-2 rounded-xl border border-rose-400/30 bg-rose-400/10 p-3 text-sm text-rose-200">
                  <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
                  {error}
                </div>
              )}
            </div>

            <div className="mt-6 flex items-center justify-between gap-3">
              <p className="text-xs text-zinc-500">حداکثر ۸۰ شرکت در هر بار واردسازی</p>
              <button
                onClick={submit}
                disabled={busy}
                className="flex items-center gap-2 rounded-xl bg-emerald-500 px-6 py-3 text-sm font-extrabold text-emerald-950 shadow-lg shadow-emerald-500/25 transition hover:bg-emerald-400 disabled:opacity-50"
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                شروع واردسازی
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
