export function cn(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

/** Deterministic 32-bit hash for stable simulation results. */
export function hashStr(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function faNum(n: number | string): string {
  return Number(n).toLocaleString("fa-IR");
}

export function faDigits(input: string): string {
  const fa = "۰۱۲۳۴۵۶۷۸۹";
  return input.replace(/\d/g, (d) => fa[Number(d)]);
}

/** Convert Persian/Arabic digits to ASCII. */
export function enDigits(input: string): string {
  const fa = "۰۱۲۳۴۵۶۷۸۹";
  const ar = "٠١٢٣٤٥٦٧٨٩";
  return input
    .replace(/[۰-۹]/g, (c) => String(fa.indexOf(c)))
    .replace(/[٠-٩]/g, (c) => String(ar.indexOf(c)));
}

export function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function normalizeUrl(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const withProto = /^https?:\/\//i.test(trimmed)
    ? trimmed
    : `https://${trimmed}`;
  try {
    const u = new URL(withProto);
    if (!u.hostname.includes(".")) return null;
    return u.toString();
  } catch {
    return null;
  }
}

export const IRAN_PHONE_RE = /(?:\+98|0098|0)?(?:9\d{9}|[1-8]\d{9})/;

export function extractPhone(text: string): string | null {
  const normalized = enDigits(text).replace(/[\s‐-‬‏‎ -‏]/g, " ");
  const m = normalized.match(/(?:\+98|0)9\d{9}/) ?? normalized.match(/0\d{10}/);
  return m ? m[0] : null;
}

export function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

/** Clipboard copy with fallback for non-secure contexts. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    throw new Error("no clipboard api");
  } catch {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      return true;
    } catch {
      return false;
    }
  }
}
