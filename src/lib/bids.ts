import type { Audit, BidSnapshot, Company, Proposal } from "@/db/schema";

/** Industry label derived from the company name — never leaks the name itself. */
export function deriveIndustry(name: string): string {
  const n = name.toLowerCase();
  if (/upvc|یوپی|یو‌پی|وین تک|پنجره|درب و پنجره/.test(n)) return "درب و پنجره UPVC";
  if (/کرکره/.test(n)) return "کرکره برقی و راهبند";
  if (/شیشه|سکوریت/.test(n)) return "شیشه سکوریت و لمینت";
  if (/آلومینیوم|نما|کرتین/.test(n)) return "نمای آلومینیوم ساختمان";
  if (/اتوماتیک/.test(n)) return "درب اتوماتیک";
  if (/پروفیل/.test(n)) return "پروفیل ساختمانی";
  if (/استیل/.test(n)) return "سازه‌های استیل";
  return "صنعت ساختمان";
}

export function makeToken(): string {
  return crypto.randomUUID().replace(/-/g, "").slice(0, 10);
}

export function makeAlias(token: string): string {
  return `پروژه سئو L-${token.slice(0, 6).toUpperCase()}`;
}

/**
 * Build the anonymized brief for the bidding widget.
 * STRICTLY excludes company name, phone, website and keywords —
 * those are only revealed after the platform commission is settled.
 */
export function buildSnapshot(
  company: Company,
  audit: Audit | null,
  proposal: Proposal | null,
): BidSnapshot {
  return {
    googleRank: company.googleRank,
    score: audit?.score ?? null,
    issuesCount: audit?.issues.length ?? 0,
    packageItems: (proposal?.pricing ?? []).map((p) => ({
      title: p.title,
      costMin: p.costMin,
      costMax: p.costMax,
    })),
    totalMin: proposal?.totalMin ?? 0,
    totalMax: proposal?.totalMax ?? 0,
    grade: proposal?.grade ?? "B",
  };
}

/** Directory of Iranian SEO agencies (seeded once). */
export const AGENCY_SEED: { name: string; specialty: string; city: string }[] = [
  { name: "آژانس سئو نمایا", specialty: "سئوی تکنیکال و Core Web Vitals", city: "تهران" },
  { name: "سئولب", specialty: "لینک‌سازی و رپورتاژ رسانه‌ای", city: "تهران" },
  { name: "راهکار دیجیتال پارسه", specialty: "سئوی صنعتی و B2B", city: "تهران" },
  { name: "آژانس رشد برتینا", specialty: "تولید محتوای تخصصی", city: "اصفهان" },
  { name: "دیده‌بان رتبه", specialty: "سئوی محلی و گوگل بیزینس", city: "تهران" },
  { name: "وب‌سلامت", specialty: "بهینه‌سازی سرعت و زیرساخت", city: "مشهد" },
  { name: "گروه دیجیتال تراز", specialty: "سئوی فروشگاهی و صنعتی", city: "تهران" },
  { name: "رسانه نقطه‌کوه", specialty: "رپورتاژ و بک‌لینک دائمی", city: "شیراز" },
  { name: "سئواستودیو پارس", specialty: "سئوی وایت‌هت سازمانی", city: "تهران" },
  { name: "مژده وب", specialty: "طراحی سایت سئومحور", city: "تبریز" },
];
