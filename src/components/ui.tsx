"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2, Radar } from "lucide-react";
import { cn, faNum } from "@/lib/utils";

/* ======================================================================
   LeadFair Design System — shared primitives for a consistent product
   ====================================================================== */

/* ---------------- Logo mark with radar sweep ---------------- */
export function LogoMark({ tone = "emerald" }: { tone?: "emerald" | "amber" }) {
  const tones = {
    emerald: {
      box: "bg-emerald-400/15 ring-emerald-400/40 text-emerald-300",
      dot: "bg-emerald-400",
      sweep: "conic-gradient(from 0deg, transparent 0deg, rgba(52,211,153,0.55) 60deg, transparent 90deg)",
    },
    amber: {
      box: "bg-amber-400/15 ring-amber-400/40 text-amber-300",
      dot: "bg-amber-400",
      sweep: "conic-gradient(from 0deg, transparent 0deg, rgba(251,191,36,0.55) 60deg, transparent 90deg)",
    },
  }[tone];
  return (
    <span className={cn("relative grid h-11 w-11 place-items-center overflow-hidden rounded-2xl ring-1", tones.box)}>
      <span
        className="logo-sweep absolute inset-0 rounded-2xl"
        style={{ background: tones.sweep }}
      />
      <Radar className="relative h-5 w-5" />
      <span className={cn("pulse-dot absolute -left-1 -top-1 h-2.5 w-2.5 rounded-full", tones.dot)} />
    </span>
  );
}

/* ---------------- Button ---------------- */
type ButtonVariant = "primary" | "amber" | "ghost" | "outline" | "danger" | "sky";
const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "bg-emerald-500 text-emerald-950 shadow-lg shadow-emerald-500/30 hover:bg-emerald-400",
  amber:
    "bg-amber-400 text-amber-950 shadow-lg shadow-amber-400/30 hover:bg-amber-300",
  ghost:
    "bg-white/10 text-white ring-1 ring-white/15 hover:bg-white/15",
  outline:
    "border border-white/15 text-zinc-300 hover:bg-white/5",
  danger:
    "bg-rose-500/15 text-rose-300 ring-1 ring-rose-400/30 hover:bg-rose-500/25",
  sky:
    "bg-sky-400/15 text-sky-300 ring-1 ring-sky-400/30 hover:bg-sky-400/25",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  icon,
  className,
  children,
  disabled,
  onClick,
  href,
  title,
}: {
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
  className?: string;
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  href?: string;
  title?: string;
}) {
  const cls = cn(
    "flex items-center justify-center gap-2 rounded-xl font-black transition disabled:opacity-40",
    size === "sm" ? "px-3.5 py-2 text-[11px]" : size === "lg" ? "px-7 py-4 text-sm" : "px-5 py-2.5 text-xs",
    BUTTON_VARIANTS[variant],
    className,
  );
  const content = (
    <>
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      {children}
    </>
  );
  if (href) {
    return (
      <Link href={href} className={cls} title={title}>
        {content}
      </Link>
    );
  }
  return (
    <button onClick={onClick} disabled={disabled || loading} className={cls} title={title}>
      {content}
    </button>
  );
}

/* ---------------- Glass panel ---------------- */
export function Panel({
  className,
  hover = false,
  children,
}: {
  className?: string;
  hover?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={cn("glass rounded-2xl p-5", hover && "glass-hover", className)}>
      {children}
    </div>
  );
}

/* ---------------- Animated counter ---------------- */
export function Counter({ value }: { value: number }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    const start = performance.now();
    const from = display;
    const delta = value - from;
    if (delta === 0) return;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / 700);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(Math.round(from + delta * eased));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return <>{faNum(display)}</>;
}

/* ---------------- Stat card ---------------- */
export function Stat({
  icon: Icon,
  label,
  value,
  suffix,
  tone = "text-zinc-200",
  delay = 0,
}: {
  icon: typeof Radar;
  label: string;
  value: number | string;
  suffix?: string;
  tone?: string;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className="glass glass-hover rounded-2xl p-4"
    >
      <Icon className="h-4 w-4 text-zinc-500" />
      <p className={cn("mt-3 text-3xl font-black tabular-nums", tone)}>
        {typeof value === "number" ? <Counter value={value} /> : value}
        {suffix && <span className="text-base font-extrabold">{suffix}</span>}
      </p>
      <p className="mt-1 text-[11px] font-bold text-zinc-500">{label}</p>
    </motion.div>
  );
}

/* ---------------- Filter chip ---------------- */
export function Chip({
  active = false,
  tone = "emerald",
  onClick,
  children,
  className,
}: {
  active?: boolean;
  tone?: "emerald" | "amber";
  onClick?: () => void;
  children: ReactNode;
  className?: string;
}) {
  const activeCls =
    tone === "amber"
      ? "bg-amber-400/15 text-amber-300 ring-amber-400/40"
      : "bg-emerald-400/15 text-emerald-300 ring-emerald-400/40";
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-full px-3.5 py-2 text-[11px] font-bold ring-1 transition",
        active ? activeCls : "bg-white/5 text-zinc-500 ring-white/10 hover:text-zinc-300",
        className,
      )}
    >
      {children}
    </button>
  );
}

/* ---------------- Status badge ---------------- */
export function Badge({
  tone,
  icon,
  children,
  className,
}: {
  tone: "emerald" | "amber" | "rose" | "sky" | "zinc";
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const tones = {
    emerald: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/30",
    amber: "bg-amber-400/10 text-amber-300 ring-amber-400/30",
    rose: "bg-rose-400/10 text-rose-300 ring-rose-400/30",
    sky: "bg-sky-400/10 text-sky-300 ring-sky-400/30",
    zinc: "bg-white/5 text-zinc-500 ring-white/10",
  }[tone];
  return (
    <span
      className={cn(
        "flex items-center gap-1 rounded-full px-3 py-1.5 text-[11px] font-black ring-1",
        tones,
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

/* ---------------- Shared site header (with routes) ---------------- */
const NAV = [
  { href: "/", label: "داشبورد لیدها" },
  { href: "/compare", label: "نبرد صفحه اول گوگل" },
  { href: "/bids", label: "بازار مناقصه کور" },
];

export function SiteHeader({
  title,
  subtitle,
  actions,
  tone = "emerald",
}: {
  title: ReactNode;
  subtitle?: string;
  actions?: ReactNode;
  tone?: "emerald" | "amber";
}) {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-40 border-b border-white/8 bg-[#070a0e]/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-5 gap-y-3 px-4 py-4 sm:px-6">
        <div className="flex items-center gap-3">
          <LogoMark tone={tone} />
          <div>
            <h1 className="text-base font-black tracking-tight">
              {title}
              <span className={cn("mr-2 text-[10px] font-bold", tone === "amber" ? "text-amber-400" : "text-emerald-400")}>
                LeadFair
              </span>
            </h1>
            {subtitle && <p className="text-[10px] text-zinc-500">{subtitle}</p>}
          </div>
        </div>

        {/* Routes */}
        <nav className="flex items-center gap-1 rounded-2xl bg-black/40 p-1 ring-1 ring-white/8">
          {NAV.map((n) => {
            const active = pathname === n.href;
            return (
              <Link
                key={n.href}
                href={n.href}
                className={cn(
                  "relative rounded-xl px-3.5 py-2 text-[11px] font-bold transition",
                  active ? "text-emerald-300" : "text-zinc-500 hover:text-zinc-300",
                )}
              >
                {active && (
                  <motion.span
                    layoutId="nav-pill"
                    className="absolute inset-0 rounded-xl bg-emerald-400/10 ring-1 ring-emerald-400/30"
                    transition={{ type: "spring", stiffness: 400, damping: 32 }}
                  />
                )}
                <span className="relative">{n.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="ms-auto flex flex-wrap items-center gap-2">{actions}</div>
      </div>
    </header>
  );
}

/* ---------------- Shared footer with full route map ---------------- */
const ROUTE_MAP: { title: string; routes: { href: string; label: string }[] }[] = [
  {
    title: "صفحات",
    routes: [
      { href: "/", label: "داشبورد لیدها" },
      { href: "/compare", label: "نبرد صفحه اول گوگل" },
      { href: "/bids", label: "بازار مناقصه کور سئو" },
      { href: "/proposal/1", label: "نمونه پیشنهادنامه چاپی" },
    ],
  },
  {
    title: "APIها",
    routes: [
      { href: "/api/health", label: "سلامت سرویس" },
      { href: "/api/companies", label: "لیست شرکت‌ها" },
      { href: "/api/serp", label: "اسکن گوگل" },
      { href: "/api/logs", label: "رویدادها" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="relative z-10 mt-16 border-t border-white/8 py-8">
      <div className="mx-auto flex max-w-7xl flex-wrap items-start justify-between gap-6 px-4 sm:px-6">
        <div>
          <div className="flex items-center gap-2">
            <LogoMark />
            <p className="text-sm font-black">لیدفِر</p>
          </div>
          <p className="mt-3 max-w-xs text-[11px] leading-6 text-zinc-500">
            اتوماسیون شکار لید نمایشگاهی، اسکن صفحه اول گوگل و صدور خودکار پیشنهادنامه سئو برای
            رسیدن کسب‌وکارها به تاپ ۱۰.
          </p>
        </div>
        {ROUTE_MAP.map((group) => (
          <div key={group.title}>
            <p className="text-[10px] font-black uppercase tracking-widest text-zinc-600">
              {group.title}
            </p>
            <ul className="mt-3 space-y-2">
              {group.routes.map((r) => (
                <li key={r.href}>
                  <Link
                    href={r.href}
                    className="text-[11px] font-bold text-zinc-400 transition hover:text-emerald-300"
                  >
                    <span dir="ltr" className="ml-1 text-zinc-600">{r.href}</span> — {r.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </footer>
  );
}
