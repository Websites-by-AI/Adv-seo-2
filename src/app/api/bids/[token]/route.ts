import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { agencies, bidRequests, companies, quotes } from "@/db/schema";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ token: string }> };

/**
 * PUBLIC widget endpoint — always anonymized.
 * Company identity is attached ONLY when the bid is revealed
 * (i.e. the platform commission has been settled).
 */
export async function GET(_req: Request, { params }: Params) {
  const { token } = await params;
  const [bid] = await db
    .select()
    .from(bidRequests)
    .where(eq(bidRequests.token, token))
    .limit(1);
  if (!bid) return NextResponse.json({ error: "فراخوان یافت نشد" }, { status: 404 });

  const bidQuotes = await db.select().from(quotes).where(eq(quotes.bidId, bid.id));

  let reveal: { name: string; phone: string | null; website: string | null } | null = null;
  if (bid.status === "revealed") {
    const [company] = await db
      .select()
      .from(companies)
      .where(eq(companies.id, bid.companyId))
      .limit(1);
    if (company) {
      reveal = { name: company.name, phone: company.phone, website: company.website };
    }
  }

  return NextResponse.json({
    bid: {
      alias: bid.alias,
      industry: bid.industry,
      city: bid.city,
      status: bid.status,
      snapshot: bid.snapshot,
      commissionPercent: bid.commissionPercent,
      createdAt: bid.createdAt,
    },
    quotesCount: bidQuotes.length,
    reveal,
  });
}

/** An SEO agency submits a price quote through the widget. */
export async function POST(req: Request, { params }: Params) {
  try {
    const { token } = await params;
    const [bid] = await db
      .select()
      .from(bidRequests)
      .where(eq(bidRequests.token, token))
      .limit(1);
    if (!bid) return NextResponse.json({ error: "فراخوان یافت نشد" }, { status: 404 });
    if (bid.status !== "open") {
      return NextResponse.json({ error: "این فراخوان بسته شده است" }, { status: 409 });
    }

    const body = (await req.json()) as {
      agencyId?: number;
      agencyName?: string;
      amountMin?: number;
      amountMax?: number;
      durationDays?: number;
      note?: string;
    };

    let agencyName = body.agencyName?.trim() ?? "";
    if (body.agencyId) {
      const [agency] = await db
        .select()
        .from(agencies)
        .where(eq(agencies.id, body.agencyId))
        .limit(1);
      if (agency) agencyName = agency.name;
    }
    const amountMin = Math.round(Number(body.amountMin));
    const amountMax = Math.round(Number(body.amountMax));
    const durationDays = Math.round(Number(body.durationDays)) || 90;

    if (!agencyName || agencyName.length < 2) {
      return NextResponse.json({ error: "نام آژانس را وارد کنید" }, { status: 400 });
    }
    if (!Number.isFinite(amountMin) || amountMin < 1_000_000) {
      return NextResponse.json({ error: "حداقل مبلغ معتبر نیست" }, { status: 400 });
    }
    if (!Number.isFinite(amountMax) || amountMax < amountMin) {
      return NextResponse.json({ error: "حداکثر مبلغ باید بزرگ‌تر از حداقل باشد" }, { status: 400 });
    }

    // One active quote per agency per bid — re-submission replaces the old one
    const bidQuotes = await db.select().from(quotes).where(eq(quotes.bidId, bid.id));
    const mine = bidQuotes.find((q) => q.agencyName === agencyName && q.status === "submitted");
    if (mine) {
      await db.delete(quotes).where(eq(quotes.id, mine.id));
    }

    const [quote] = await db
      .insert(quotes)
      .values({
        bidId: bid.id,
        agencyId: body.agencyId ?? null,
        agencyName,
        amountMin,
        amountMax,
        durationDays,
        note: body.note?.trim() || null,
      })
      .returning();

    return NextResponse.json({ ok: true, quoteId: quote.id });
  } catch (err) {
    console.error("quote submit error", err);
    return NextResponse.json({ error: "خطا در ثبت قیمت" }, { status: 500 });
  }
}
