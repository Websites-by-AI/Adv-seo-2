import * as cheerio from "cheerio";
import { domainOf, hashStr } from "./utils";
import type { SerpEntry } from "@/db/schema";

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";

async function safeFetch(url: string, ms = 7000): Promise<string> {
  const res = await fetch(url, {
    signal: AbortSignal.timeout(ms),
    headers: {
      "User-Agent": UA,
      "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.5",
      Accept: "text/html,application/xhtml+xml",
    },
    redirect: "follow",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`http ${res.status}`);
  return res.text();
}

/* ---------------- Live engines ---------------- */

async function tryGoogle(keyword: string): Promise<SerpEntry[]> {
  const html = await safeFetch(
    `https://www.google.com/search?q=${encodeURIComponent(keyword)}&num=20&hl=fa&gl=ir`,
  );
  if (/captcha|unusual traffic|consent/i.test(html)) throw new Error("blocked");
  const $ = cheerio.load(html);
  const out: SerpEntry[] = [];
  const seen = new Set<string>();
  $("a").each((_, el) => {
    const h3 = $(el).find("h3").first();
    if (!h3.length) return;
    let href = $(el).attr("href") ?? "";
    const m = href.match(/\/url\?q=([^&]+)/);
    if (m) href = decodeURIComponent(m[1]);
    if (!/^https?:\/\//i.test(href) || /google\./i.test(href)) return;
    const domain = domainOf(href);
    if (seen.has(domain)) return;
    seen.add(domain);
    out.push({
      position: out.length + 1,
      title: h3.text().trim(),
      url: href,
      domain,
      snippet:
        $(el).closest("div").parent().find("[data-sncf], .VwiC3b").first().text().trim() ||
        null,
    });
  });
  if (out.length < 5) throw new Error("parse failed");
  return out.slice(0, 10);
}

async function tryDuckDuckGo(keyword: string): Promise<SerpEntry[]> {
  const html = await safeFetch(
    `https://html.duckduckgo.com/html/?q=${encodeURIComponent(keyword)}&kl=ir-fa`,
  );
  const $ = cheerio.load(html);
  const out: SerpEntry[] = [];
  const seen = new Set<string>();
  $(".result").each((_, el) => {
    const a = $(el).find("a.result__a").first();
    let href = a.attr("href") ?? "";
    const m = href.match(/uddg=([^&]+)/);
    if (m) href = decodeURIComponent(m[1]);
    if (!/^https?:\/\//i.test(href)) return;
    const title = a.text().trim();
    if (!title) return;
    const domain = domainOf(href);
    if (seen.has(domain)) return;
    seen.add(domain);
    out.push({
      position: out.length + 1,
      title,
      url: href,
      domain,
      snippet: $(el).find(".result__snippet").first().text().trim() || null,
    });
  });
  if (out.length < 5) throw new Error("parse failed");
  return out.slice(0, 10);
}

async function tryBing(keyword: string): Promise<SerpEntry[]> {
  const html = await safeFetch(
    `https://www.bing.com/search?q=${encodeURIComponent(keyword)}&count=20&setlang=fa`,
  );
  const $ = cheerio.load(html);
  const out: SerpEntry[] = [];
  const seen = new Set<string>();
  $("li.b_algo").each((_, el) => {
    const a = $(el).find("h2 a").first();
    const href = a.attr("href") ?? "";
    const title = a.text().trim();
    if (!/^https?:\/\//i.test(href) || !title) return;
    const domain = domainOf(href);
    if (seen.has(domain)) return;
    seen.add(domain);
    out.push({
      position: out.length + 1,
      title,
      url: href,
      domain,
      snippet: $(el).find(".b_caption p").first().text().trim() || null,
    });
  });
  if (out.length < 5) throw new Error("parse failed");
  return out.slice(0, 10);
}

/* ---------------- Simulated fallback ---------------- */

const FILLER: { title: string; domain: string }[] = [
  { title: "وین‌پنجره | تولیدی تخصصی درب و پنجره UPVC دوجداره", domain: "winpanjere.ir" },
  { title: "مرکز تخصصی پروفیل یوپی‌وی‌سی ایران | قیمت و نصب", domain: "upvc-center.ir" },
  { title: "تک‌پروفیل | واردکننده پروفیل و یراق‌آلات آلمانی", domain: "takprofile.com" },
  { title: "پنجره‌گستر پارس | طراحی، تولید و اجرای پنجره دوجداره", domain: "panjerehgostar.ir" },
  { title: "مدرن نما سازه | کرتین وال و نمای آلومینیومی ساختمان", domain: "modernnama.ir" },
  { title: "آلپ‌وین | پنجره‌های ترمال‌بریک و لمینت", domain: "alpwin.ir" },
  { title: "مارکت تخصصی درب و پنجره | مقایسه قیمت برندها", domain: "doorwinmarket.ir" },
  { title: "یوپی‌وی‌سی‌لند | فروش آنلاین پروفیل و اکسسوری", domain: "upvcland.ir" },
  { title: "آرین ویندو | پنجره‌های ترکیبی آلومینیوم-چوب", domain: "arianwindow.com" },
  { title: "پروفیل‌کالا | بزرگ‌ترین مرجع پروفیل ساختمانی", domain: "profilekala.ir" },
  { title: "شیشه‌نما | سکوریت، لمینت و شیشه دوجداره", domain: "shishenama.ir" },
  { title: "گروه صنعتی وین‌سازه | درب‌های اتوماتیک و کرکره", domain: "winsazeh.ir" },
];

export interface ExhibitorLite {
  id: number;
  name: string;
  website: string | null;
  googleRank: number | null;
}

export function simulateSerp(
  keyword: string,
  exhibitors: ExhibitorLite[],
): SerpEntry[] {
  const slots = new Map<number, SerpEntry>();
  // Place exhibitors that are genuinely (simulated) on page 1
  for (const ex of exhibitors) {
    if (ex.googleRank !== null && ex.googleRank <= 10 && ex.website) {
      const domain = domainOf(ex.website);
      slots.set(ex.googleRank, {
        position: ex.googleRank,
        title: `${ex.name} | سایت رسمی`,
        url: ex.website,
        domain,
        snippet: null,
        fromExhibitor: true,
        matchedCompanyId: ex.id,
        matchedCompanyName: ex.name,
      });
    }
  }
  // Fill remaining positions with deterministic filler competitors
  const h = hashStr(keyword);
  const ordered = FILLER.map((f, i) => ({ f, r: (h >>> (i % 16)) % 89 }))
    .sort((a, b) => a.r - b.r)
    .map((x) => x.f);
  let fi = 0;
  for (let pos = 1; pos <= 10; pos++) {
    if (slots.has(pos)) continue;
    const f = ordered[fi % ordered.length];
    fi++;
    slots.set(pos, {
      position: pos,
      title: f.title,
      url: `https://www.${f.domain}/`,
      domain: f.domain,
      snippet: null,
    });
  }
  return [...slots.values()].sort((a, b) => a.position - b.position).slice(0, 10);
}

/* ---------------- Main scan ---------------- */

export async function scanSerp(
  keyword: string,
  exhibitors: ExhibitorLite[],
): Promise<{ entries: SerpEntry[]; mode: "live" | "simulated"; engine: string }> {
  const engines: [string, (k: string) => Promise<SerpEntry[]>][] = [
    ["google", tryGoogle],
    ["duckduckgo", tryDuckDuckGo],
    ["bing", tryBing],
  ];
  for (const [name, fn] of engines) {
    try {
      const entries = await fn(keyword);
      return { entries: entries.map((e, i) => ({ ...e, position: i + 1 })), mode: "live", engine: name };
    } catch {
      // try next engine
    }
  }
  return {
    entries: simulateSerp(keyword, exhibitors),
    mode: "simulated",
    engine: "simulated",
  };
}

/* ---------------- Cross-matching ---------------- */

const GENERIC_TOKENS = new Set([
  "شرکت",
  "گروه",
  "صنایع",
  "تولیدی",
  "تجارت",
  "بازرگانی",
  "سهامی",
  "خاص",
  "عام",
  "بین‌المللی",
  "خدمات",
  "مهندسی",
  // Industry-generic words — matching on these alone is meaningless
  "درب",
  "پنجره",
  "پروفیل",
  "یوپی‌وی‌سی",
  "یوپی",
  "وی",
  "سی",
  "پی",
  "upvc",
  "آلومینیوم",
  "شیشه",
  "دوجداره",
  "نما",
  "کرکره",
  "ساختمان",
  "ساختمانی",
  "تهران",
  "ایران",
  "فروش",
  "قیمت",
  "نصب",
  "تولید",
  "اجرای",
  "انواع",
  "مدرن",
  "استیل",
  "برقی",
  "اتوماتیک",
]);

function normalizeFa(s: string): string {
  return s.replace(/ي/g, "ی").replace(/ك/g, "ک").replace(/[‌‏‎]/g, " ").toLowerCase();
}

/** Does an exhibitor appear among the SERP entries? Returns position or null. */
export function matchExhibitorPosition(
  exhibitor: ExhibitorLite,
  entries: SerpEntry[],
): number | null {
  // 1) exact domain match
  if (exhibitor.website) {
    const d = domainOf(exhibitor.website);
    const hit = entries.find((e) => e.domain === d);
    if (hit) return hit.position;
  }
  // 2) fuzzy brand match in titles/snippets — only distinctive tokens count
  const tokens = normalizeFa(exhibitor.name)
    .split(/\s+/)
    .filter((t) => t.length > 1 && !GENERIC_TOKENS.has(t));
  if (tokens.length === 0) return null;
  const containsToken = (hay: string, t: string) =>
    t.length > 2
      ? hay.includes(t)
      : new RegExp(`(^|\\s)${t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(\\s|$)`).test(hay);
  for (const e of entries) {
    const hay = ` ${normalizeFa(`${e.title} ${e.snippet ?? ""}`)} `;
    const hits = tokens.filter((t) => containsToken(hay, t)).length;
    if (hits >= Math.min(2, tokens.length) || hay.includes(normalizeFa(exhibitor.name).trim())) {
      return e.position;
    }
  }
  return null;
}
