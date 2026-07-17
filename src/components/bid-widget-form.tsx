"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Send, Loader2, CircleCheck, CircleAlert, Building2 } from "lucide-react";

interface AgencyLite {
  id: number;
  name: string;
  specialty: string | null;
  city: string | null;
}

export function BidQuoteForm({
  token,
  agencies,
}: {
  token: string;
  agencies: AgencyLite[];
}) {
  const [agencyId, setAgencyId] = useState<number | "">("");
  const [customName, setCustomName] = useState("");
  const [amountMin, setAmountMin] = useState("");
  const [amountMax, setAmountMax] = useState("");
  const [durationDays, setDurationDays] = useState("90");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bids/${token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agencyId: agencyId === "" ? undefined : agencyId,
          agencyName: agencyId === "" ? customName : undefined,
          amountMin: Number(amountMin.replace(/[,،\s]/g, "")),
          amountMax: Number(amountMax.replace(/[,،\s]/g, "")),
          durationDays: Number(durationDays) || 90,
          note: note || undefined,
        }),
      });
      const d = await res.json();
      if (!res.ok) {
        setError(d.error ?? "خطا در ثبت قیمت");
        return;
      }
      setDone(true);
    } catch {
      setError("خطای ارتباط با سرور");
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        className="rounded-3xl border border-emerald-300 bg-emerald-50 p-8 text-center"
      >
        <CircleCheck className="mx-auto h-12 w-12 text-emerald-500" />
        <h3 className="mt-4 text-lg font-black text-emerald-800">قیمت شما ثبت شد</h3>
        <p className="mt-2 text-sm leading-7 text-emerald-700">
          پیشنهاد شما به‌صورت محرمانه برای بررسی به لیدفِر ارسال شد. در صورت پذیرش و تسویه پورسانت
          پلتفرم، اطلاعات کامل کارفرما برای شما آشکار می‌شود.
        </p>
      </motion.div>
    );
  }

  const inputCls =
    "w-full rounded-xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-200";

  return (
    <div className="space-y-4">
      <div>
        <label className="mb-1.5 block text-xs font-black text-zinc-700">آژانس سئوی شما</label>
        <select
          value={agencyId}
          onChange={(e) => setAgencyId(e.target.value ? Number(e.target.value) : "")}
          className={inputCls}
        >
          <option value="">— انتخاب از فهرست آژانس‌های سئو ایران —</option>
          {agencies.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} — {a.specialty} ({a.city})
            </option>
          ))}
        </select>
      </div>
      {agencyId === "" && (
        <div>
          <label className="mb-1.5 block text-xs font-black text-zinc-700">یا نام آژانس دستی</label>
          <input
            value={customName}
            onChange={(e) => setCustomName(e.target.value)}
            placeholder="نام کامل آژانس سئو"
            className={inputCls}
          />
        </div>
      )}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1.5 block text-xs font-black text-zinc-700">حداقل مبلغ (تومان)</label>
          <input
            value={amountMin}
            onChange={(e) => setAmountMin(e.target.value)}
            dir="ltr"
            inputMode="numeric"
            placeholder="80,000,000"
            className={`${inputCls} text-left`}
          />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-black text-zinc-700">حداکثر مبلغ (تومان)</label>
          <input
            value={amountMax}
            onChange={(e) => setAmountMax(e.target.value)}
            dir="ltr"
            inputMode="numeric"
            placeholder="150,000,000"
            className={`${inputCls} text-left`}
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1.5 block text-xs font-black text-zinc-700">مدت اجرا (روز)</label>
          <input
            value={durationDays}
            onChange={(e) => setDurationDays(e.target.value)}
            dir="ltr"
            inputMode="numeric"
            className={`${inputCls} text-left`}
          />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-black text-zinc-700">توضیح (اختیاری)</label>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="شرح تفاوت رویکرد شما…"
            className={inputCls}
          />
        </div>
      </div>
      {error && (
        <p className="flex items-center gap-2 rounded-xl bg-rose-50 px-4 py-3 text-xs font-bold text-rose-700 ring-1 ring-rose-200">
          <CircleAlert className="h-4 w-4" /> {error}
        </p>
      )}
      <button
        onClick={submit}
        disabled={busy}
        className="flex w-full items-center justify-center gap-2 rounded-2xl bg-zinc-900 px-6 py-4 text-sm font-black text-white shadow-lg transition hover:bg-zinc-800 disabled:opacity-50"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        ثبت قیمت پیشنهادی
      </button>
      <p className="flex items-start gap-2 text-[10px] leading-5 text-zinc-400">
        <Building2 className="mt-0.5 h-3 w-3 shrink-0" />
        ارسال قیمت به معنای پذیرش شرط محرمانگی است: تا قبل از تسویه پورسانت پلتفرم، تماس مستقیم یا
        شناسایی کارفرما ممنوع است.
      </p>
    </div>
  );
}
