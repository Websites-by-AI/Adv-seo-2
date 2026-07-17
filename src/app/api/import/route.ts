import { NextResponse } from "next/server";
import { db } from "@/db";
import { companies, exhibitions, activityLogs } from "@/db/schema";
import {
  parseCompaniesFromHtml,
  parseManualList,
  SAMPLE_COMPANIES,
  type ParsedCompany,
} from "@/lib/parse";

export const dynamic = "force-dynamic";

interface ImportBody {
  mode: "url" | "html" | "manual" | "sample";
  url?: string;
  html?: string;
  text?: string;
  exhibitionName?: string;
}

export async function POST(req: Request) {
  try {
    const body = (await req.json()) as ImportBody;
    let parsed: ParsedCompany[] = [];
    let sourceUrl: string | null = null;
    let htmlFetchNote: string | null = null;

    if (body.mode === "url") {
      if (!body.url) {
        return NextResponse.json({ error: "آدرس صفحه نمایشگاه را وارد کنید" }, { status: 400 });
      }
      sourceUrl = body.url;
      try {
        const res = await fetch(body.url, {
          signal: AbortSignal.timeout(12000),
          headers: {
            "User-Agent":
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "fa-IR,fa;q=0.9",
          },
        });
        if (!res.ok) throw new Error(String(res.status));
        const html = await res.text();
        parsed = parseCompaniesFromHtml(html, body.url);
      } catch {
        htmlFetchNote =
          "دریافت مستقیم صفحه از سرور ممکن نشد. لطفاً سورس صفحه (HTML) را کپی و در تب «کد HTML» جای‌گذاری کنید.";
      }
    } else if (body.mode === "html") {
      if (!body.html || body.html.length < 100) {
        return NextResponse.json({ error: "کد HTML معتبر وارد کنید" }, { status: 400 });
      }
      sourceUrl = body.url ?? null;
      parsed = parseCompaniesFromHtml(body.html, body.url);
    } else if (body.mode === "manual") {
      if (!body.text) {
        return NextResponse.json({ error: "لیست شرکت‌ها خالی است" }, { status: 400 });
      }
      parsed = parseManualList(body.text);
    } else if (body.mode === "sample") {
      parsed = SAMPLE_COMPANIES.map((c) => ({ ...c }));
    }

    if (parsed.length === 0) {
      return NextResponse.json(
        {
          error:
            htmlFetchNote ??
            "هیچ شرکتی در ورودی شناسایی نشد. ساختار صفحه را بررسی کنید یا از ورود دستی استفاده کنید.",
        },
        { status: 422 },
      );
    }

    const [exhibition] = await db
      .insert(exhibitions)
      .values({
        name:
          body.exhibitionName?.trim() ||
          (body.mode === "sample"
            ? "نمایشگاه درب و پنجره تهران ۱۴۰۴ (نمونه)"
            : body.mode === "url" && body.url
              ? new URL(body.url).hostname
              : "واردسازی دستی"),
        sourceUrl,
      })
      .returning();

    // Dedupe against existing company names
    const existing = await db.select({ name: companies.name }).from(companies);
    const existingKeys = new Set(existing.map((c) => c.name.replace(/\s/g, "")));
    const fresh = parsed.filter((c) => !existingKeys.has(c.name.replace(/\s/g, "")));

    if (fresh.length > 0) {
      await db.insert(companies).values(
        fresh.map((c) => ({
          exhibitionId: exhibition.id,
          name: c.name,
          phone: c.phone,
          website: c.website,
          sourceUrl: c.sourceUrl,
          status: "new",
        })),
      );
    }

    await db.insert(activityLogs).values({
      level: "success",
      message: `واردسازی «${exhibition.name}»: ${fresh.length} شرکت جدید${parsed.length - fresh.length > 0 ? ` (${parsed.length - fresh.length} تکراری نادیده گرفته شد)` : ""}`,
    });

    return NextResponse.json({
      ok: true,
      exhibitionId: exhibition.id,
      inserted: fresh.length,
      skipped: parsed.length - fresh.length,
      total: parsed.length,
      note: htmlFetchNote,
    });
  } catch (err) {
    console.error("import error", err);
    return NextResponse.json({ error: "خطای داخلی هنگام واردسازی داده" }, { status: 500 });
  }
}
