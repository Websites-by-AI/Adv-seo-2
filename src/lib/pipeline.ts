import * as cheerio from "cheerio";
import { domainOf, hashStr, normalizeUrl, sleep } from "./utils";
import type { Company } from "@/db/schema";

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";

const SEARCH_BLOCKLIST =
  /(google\.|youtube\.|instagram\.|facebook\.|twitter\.|linkedin\.|aparat\.|iranadfair\.|divar\.|sheypoor\.|torob\.|emalls\.|tebyan\.|namnak\.|zoomit\.|digiato\.|wikipedia\.|sanisede\.|sedayebourse\.)/i;

async function fetchWithTimeout(url: string, ms: number): Promise<Response> {
  return fetch(url, {
    signal: AbortSignal.timeout(ms),
    headers: {
      "User-Agent": UA,
      "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.5",
      Accept: "text/html,application/xhtml+xml",
    },
    redirect: "follow",
    cache: "no-store",
  });
}

export interface RankResult {
  position: number;
  onFirstPage: boolean;
  mode: "live" | "simulated";
  discoveredWebsite: string | null;
}

/** Try a real Google search; fall back to a deterministic simulation. */
export async function checkGoogleRank(company: {
  name: string;
  website: string | null;
}): Promise<RankResult> {
  const keyword = company.name;
  try {
    const q = encodeURIComponent(keyword);
    const res = await fetchWithTimeout(
      `https://www.google.com/search?q=${q}&num=30&hl=fa&gl=ir`,
      6000,
    );
    if (!res.ok) throw new Error(`google ${res.status}`);
    const html = await res.text();
    if (html.includes("captcha") || html.includes("unusual traffic")) {
      throw new Error("blocked");
    }
    const $ = cheerio.load(html);
    const links: string[] = [];
    $("a[href]").each((_, el) => {
      let href = $(el).attr("href") ?? "";
      const urlMatch = href.match(/\/url\?q=([^&]+)/);
      if (urlMatch) href = decodeURIComponent(urlMatch[1]);
      if (/^https?:\/\//i.test(href) && !/google\./i.test(href)) {
        links.push(href);
      }
    });
    if (links.length === 0) throw new Error("no results parsed");

    // Determine the company's own domain (known or inferred later)
    const known = company.website ? domainOf(company.website) : null;
    const tokens = keyword
      .replace(/[‌‏]/g, " ")
      .split(/\s+/)
      .filter((t) => t.length > 2);

    let position: number | null = null;
    const seen = new Set<string>();
    let idx = 0;
    for (const link of links) {
      const d = domainOf(link);
      if (seen.has(d)) continue;
      seen.add(d);
      idx++;
      if (known && d === known) {
        position = idx;
        break;
      }
    }
    // First result that is not a directory/social portal = likely their site
    const ownCandidate =
      links.find((l) => !SEARCH_BLOCKLIST.test(l)) ?? null;

    if (position === null) {
      // If their known site does not show up in top-30 at all:
      position = known ? 31 : null;
    }
    if (position === null) {
      // No known website: if a unique candidate domain appears whose host
      // shares a token with the brand, treat it as theirs.
      if (ownCandidate) {
        const host = domainOf(ownCandidate);
        const hostAscii = host.toLowerCase();
        const hit = tokens.some((t) =>
          /[a-z]/i.test(t) ? hostAscii.includes(t.toLowerCase()) : false,
        );
        position = hit ? 1 : 31;
      } else {
        position = 31;
      }
    }
    return {
      position,
      onFirstPage: position <= 10,
      mode: "live",
      discoveredWebsite: known ? null : ownCandidate,
    };
  } catch {
    // ---- Deterministic simulation (offline / blocked) ----
    const h = hashStr(keyword);
    const bucket = h % 100;
    // ~30% land on page 1, the rest deep in the results
    const position =
      bucket < 30 ? (h % 10) + 1 : 11 + ((h >>> 3) % 60);
    const onFirstPage = position <= 10;
    // Simulated discovery: ~45% have a findable site deeper than page 1
    const discoveredWebsite =
      !company.website && !onFirstPage && (h >>> 5) % 100 < 45
        ? null // keep honest: we can't fabricate real domains
        : null;
    return {
      position,
      onFirstPage,
      mode: "simulated",
      discoveredWebsite,
    };
  }
}

export interface AuditResult {
  url: string | null;
  httpStatus: number | null;
  loadTimeMs: number | null;
  title: string | null;
  metaDescription: string | null;
  hasTitle: boolean;
  hasMetaDescription: boolean;
  hasH1: boolean;
  hasViewport: boolean;
  isHttps: boolean;
  hasJsonLd: boolean;
  hasFaqSchema: boolean;
  wordCount: number;
  h1Count: number;
  score: number;
  mode: "live" | "no-site" | "unreachable";
  issues: string[];
}

export async function auditWebsite(
  website: string | null,
  companyName: string,
): Promise<AuditResult> {
  if (!website) {
    return {
      url: null,
      httpStatus: null,
      loadTimeMs: null,
      title: null,
      metaDescription: null,
      hasTitle: false,
      hasMetaDescription: false,
      hasH1: false,
      hasViewport: false,
      isHttps: false,
      hasJsonLd: false,
      hasFaqSchema: false,
      wordCount: 0,
      h1Count: 0,
      score: 8,
      mode: "no-site",
      issues: [
        "وب‌سایت اختصاصی برای این کسب‌وکار پیدا نشد",
        "غیبت کامل در نتایج جستجوی گوگل و گوگل مپ",
        "سهم صفر از ترافیک رایگان جستجو در مقایسه با رقبا",
        "عدم وجود زیرساخت برای تبلیغات هدفمند و ریمارکتینگ",
      ],
    };
  }

  const url = normalizeUrl(website) ?? website;
  try {
    const started = Date.now();
    const res = await fetchWithTimeout(url, 9000);
    const loadTimeMs = Date.now() - started;
    const html = await res.text();
    const $ = cheerio.load(html);

    const title = $("title").first().text().trim() || null;
    const metaDescription =
      $('meta[name="description"]').attr("content")?.trim() || null;
    const h1Count = $("h1").length;
    const hasViewport = $('meta[name="viewport"]').length > 0;
    const jsonLdTypes: string[] = [];
    $('script[type="application/ld+json"]').each((_, el) => {
      const txt = $(el).text();
      const m = txt.match(/"@type"\s*:\s*"([^"]+)"/g);
      if (m) jsonLdTypes.push(...m);
    });
    const bodyText = $("body").text().replace(/\s+/g, " ").trim();
    const wordCount = bodyText ? bodyText.split(" ").length : 0;

    const isHttps = url.startsWith("https://");
    const issues: string[] = [];
    let score = 100;

    const dock = (points: number, issue: string) => {
      score -= points;
      issues.push(issue);
    };
    if (!title) dock(20, "صفحه اصلی فاقد تگ Title است");
    else if (title.length < 25)
      dock(8, `تگ Title بسیار کوتاه است (${title.length} کاراکتر)`);
    else if (!companyName.split(" ")[0] || !title.includes(companyName.split(" ")[1] ?? companyName.split(" ")[0]))
      dock(5, "نام برند در تگ Title دیده نمی‌شود");
    if (!metaDescription) dock(15, "متا دیسکریپشن تعریف نشده است");
    if (h1Count === 0) dock(15, "تگ H1 در صفحه اصلی وجود ندارد");
    if (h1Count > 1) dock(5, `چند تگ H1 (${h1Count} عدد) رتبه را تضعیف می‌کند`);
    if (!hasViewport) dock(10, "تگ Viewport موبایل تنظیم نشده است");
    if (!isHttps) dock(12, "پروتکل امن HTTPS فعال نیست");
    if (jsonLdTypes.length === 0) dock(10, "داده ساختاریافته Schema.org ندارد");
    if (!jsonLdTypes.some((t) => t.toLowerCase().includes("faq")))
      dock(4, "اسکیمای FAQ برای گرفتن جایگاه صفر استفاده نشده است");
    if (wordCount < 300) dock(12, `محتوای صفحه اصلی بسیار کم است (~${wordCount} کلمه)`);
    if (loadTimeMs > 3000)
      dock(10, `سرعت بارگذاری بالا است (${(loadTimeMs / 1000).toFixed(1)} ثانیه)`);
    if (!res.ok) dock(20, `پاسخ سرور ناموفق است (کد ${res.status})`);

    return {
      url,
      httpStatus: res.status,
      loadTimeMs,
      title,
      metaDescription,
      hasTitle: Boolean(title),
      hasMetaDescription: Boolean(metaDescription),
      hasH1: h1Count > 0,
      hasViewport,
      isHttps,
      hasJsonLd: jsonLdTypes.length > 0,
      hasFaqSchema: jsonLdTypes.some((t) => t.toLowerCase().includes("faq")),
      wordCount,
      h1Count,
      score: Math.max(5, Math.min(100, score)),
      mode: "live",
      issues,
    };
  } catch {
    return {
      url,
      httpStatus: null,
      loadTimeMs: null,
      title: null,
      metaDescription: null,
      hasTitle: false,
      hasMetaDescription: false,
      hasH1: false,
      hasViewport: false,
      isHttps: url.startsWith("https://"),
      hasJsonLd: false,
      hasFaqSchema: false,
      wordCount: 0,
      h1Count: 0,
      score: 12,
      mode: "unreachable",
      issues: [
        "وب‌سایت در زمان بررسی در دسترس نبود (خطای اتصال)",
        "احتمال قطعی مکرر، مشکل هاست یا عدم تمدید دامنه",
        "هر ساعت از دسترس خارج بودن، اعتماد گوگل و مشتری را کاهش می‌دهد",
      ],
    };
  }
}

export async function politeDelay() {
  await sleep(300 + Math.random() * 400);
}

export function suggestKeywords(company: Pick<Company, "name">): string[] {
  const h = hashStr(company.name);
  const base = company.name
    .replace(/^(شرکت|گروه|تولیدی|تجارت|بازرگانی|صنایع)\s+/i, "")
    .trim();
  const pool = [
    base,
    `قیمت ${base}`,
    `خرید ${base}`,
    `${base} تهران`,
    `نمایندگی ${base}`,
    `${base} با کیفیت`,
    `بهترین ${base}`,
    `فروش ${base}`,
    `${base} ارزان`,
    `گالری ${base}`,
  ];
  // deterministic shuffle, keep 6
  return pool
    .map((k, i) => ({ k, r: (h >>> i) % 97 }))
    .sort((a, b) => a.r - b.r)
    .slice(0, 6)
    .map((x) => x.k);
}
