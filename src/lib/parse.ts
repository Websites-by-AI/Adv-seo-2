import * as cheerio from "cheerio";
import type { Element } from "domhandler";
import { extractPhone, normalizeUrl } from "./utils";

export interface ParsedCompany {
  name: string;
  phone: string | null;
  website: string | null;
  sourceUrl: string | null;
}

const BLOCKED_HREF =
  /(ad_category|wp-admin|wp-login|wp-content|\/feed|#|javascript:|mailto:|telegram\.me|instagram\.com|aparat\.com|facebook\.com|twitter\.com|linkedin\.com|youtube\.com|\.jpg|\.jpeg|\.png|\.webp|\.svg|login|register|my-account|cart|checkout)/i;

const NOISE_TEXT =
  /^(خانه|صفحه اصلی|تماس|درباره|بلاگ|وبلاگ|جستجو|ورود|ثبت نام|ثبت‌نام|نمایش همه|مشاهده همه|ادامه مطلب|آرشیو|دسته‌بندی|دسته بندی)$/;

const COMPANY_HINT =
  /(شرکت|گروه|صنایع|تولیدی|تجارت|بازرگانی|صنعت|درب|پنجره|UPVC|یوپی‌وی‌سی|پروفیل|آلومینیوم|شیشه|نما|درب اتوماتیک|کرکره)/i;

function cleanName(raw: string): string {
  return raw
    .replace(/\s+/g, " ")
    .replace(/[‌‏‎]/g, " ")
    .trim()
    .slice(0, 90);
}

/**
 * Extract company entries from an exhibition listing HTML page
 * (generic heuristics tuned for AdForest / WordPress listing themes).
 */
export function parseCompaniesFromHtml(
  html: string,
  baseUrl?: string,
): ParsedCompany[] {
  const $ = cheerio.load(html);
  $("script, style, noscript, header, footer, nav, form, aside").remove();

  const docPhone = extractPhone($.text());
  const found = new Map<string, ParsedCompany>();

  const register = (nameRaw: string, el: Element | null) => {
    const name = cleanName(nameRaw);
    if (name.length < 4 || name.length > 90) return;
    if (NOISE_TEXT.test(name)) return;
    const key = name.replace(/\s/g, "");
    if (found.has(key)) return;

    let href: string | null = null;
    let phone: string | null = null;
    let website: string | null = null;
    if (el) {
      href = $(el).attr("href") ?? null;
      const $card = $(el).closest(
        "article, li, .card, .listing, .ad, .item, .category-grid-box, [class*='box'], [class*='card']",
      );
      const scopeText = ($card.length ? $card.text() : $(el).parent().text()) || "";
      phone = extractPhone(scopeText);
      // look for explicit external website links inside the card
      ($card.length ? $card : $(el).parent())
        .find("a[href^='http']")
        .each((_, a) => {
          const h = $(a).attr("href") ?? "";
          if (
            baseUrl &&
            !h.includes(new URL(baseUrl).hostname) &&
            !BLOCKED_HREF.test(h)
          ) {
            website = website ?? normalizeUrl(h);
          }
        });
    }
    if (href && BLOCKED_HREF.test(href)) href = null;
    if (href && href.startsWith("/") && baseUrl) {
      href = new URL(href, baseUrl).toString();
    }
    if (href && !/^https?:\/\//i.test(href)) href = null;

    // Name must look like a business, or carry a phone/link signal
    if (!COMPANY_HINT.test(name) && !phone && !href) return;

    found.set(key, { name, phone, website, sourceUrl: href });
  };

  // Pass 1: headings + links inside listing-like containers
  $("article a[href], .ad-title a[href], h2 a[href], h3 a[href], h4 a[href], .categorized-ads a[href], .ads-listing a[href], [class*='listing'] a[href]").each(
    (_, el) => register($(el).text(), el),
  );

  // Pass 2 (fallback): every decent anchor on the page
  if (found.size < 3) {
    $("a[href]").each((_, el) => register($(el).text(), el));
  }

  let list = [...found.values()].slice(0, 80);
  // Attach a document-level phone to the first phone-less entry as a last resort
  if (docPhone && list.length > 0 && !list.some((c) => c.phone)) {
    list = list.map((c, i) => (i === 0 ? { ...c, phone: docPhone } : c));
  }
  return list;
}

/** Parse manual text input: one company per line, `نام | تلفن | وب‌سایت`. */
export function parseManualList(text: string): ParsedCompany[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length >= 3)
    .slice(0, 200)
    .map((line) => {
      const parts = line.split(/[|\t،,]/).map((p) => p.trim());
      const name = cleanName(parts[0] ?? "");
      const phone = extractPhone(line);
      const urlPart = parts.find((p) => /\.(ir|com|net|co|org)(\b|\/|$)/i.test(p));
      return {
        name,
        phone,
        website: urlPart ? normalizeUrl(urlPart) : null,
        sourceUrl: null,
      };
    })
    .filter((c) => c.name.length >= 3);
}

/** Sample exhibitors for one-click demo import. */
export const SAMPLE_COMPANIES: ParsedCompany[] = [
  { name: "شرکت پنجره سازان آریا", phone: "09123456701", website: null, sourceUrl: null },
  { name: "تولیدی درب و پنجره یوپی‌وی‌سی الوند", phone: "09123456702", website: null, sourceUrl: null },
  { name: "گروه صنایع UPVC تهران پروفیل", phone: "02155667701", website: null, sourceUrl: null },
  { name: "شرکت تک‌ویو پنجره دوجداره", phone: "09123456704", website: "https://upvcmag.ir", sourceUrl: null },
  { name: "وین تک پنجره پارسیان", phone: "09123456705", website: null, sourceUrl: null },
  { name: "صنایع پروفیل پارس گیلان", phone: "01333445506", website: null, sourceUrl: null },
  { name: "شرکت بازرگانی کاوه پروفیل", phone: "09123456707", website: null, sourceUrl: null },
  { name: "یاشیل پنجره آذربایجان", phone: "04133445508", website: null, sourceUrl: null },
  { name: "گروه نمای مدرن سازان", phone: "09123456709", website: "https://yekgap.com", sourceUrl: null },
  { name: "درب اتوماتیک صدرا الکتریک", phone: "02188776610", website: null, sourceUrl: null },
  { name: "شیشه سکوریت البرز تراست", phone: "09123456711", website: null, sourceUrl: null },
  { name: "شرکت آلومینیوم ساختمانی رادین", phone: "09123456712", website: null, sourceUrl: null },
  { name: "تجارت کرکره برقی پارسه", phone: "09123456713", website: null, sourceUrl: null },
  { name: "صنعت پنجره استیل آرشام", phone: "09123456714", website: null, sourceUrl: null },
];
