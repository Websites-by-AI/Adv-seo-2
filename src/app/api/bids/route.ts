import { NextResponse } from "next/server";
import { desc, eq } from "drizzle-orm";
import { db } from "@/db";
import { companies, audits, proposals, bidRequests, quotes, activityLogs } from "@/db/schema";
import { buildSnapshot, deriveIndustry, makeAlias, makeToken } from "@/lib/bids";

export const dynamic = "force-dynamic";

/** Owner view: every bid with the REAL company name + all quotes. */
export async function GET() {
  const bids = await db
    .select({ bid: bidRequests, company: companies })
    .from(bidRequests)
    .leftJoin(companies, eq(companies.id, bidRequests.companyId))
    .orderBy(desc(bidRequests.id))
    .limit(100);

  const allQuotes = await db.select().from(quotes).orderBy(desc(quotes.id)).limit(300);

  const items = bids.map((b) => ({
    ...b.bid,
    companyName: b.company?.name ?? "—",
    companyPhone: b.company?.phone ?? null,
    companyWebsite: b.company?.website ?? null,
    quotes: allQuotes.filter((q) => q.bidId === b.bid.id),
  }));

  return NextResponse.json({ bids: items });
}

/** Create a blind bid request for a company (anonymized brief). */
export async function POST(req: Request) {
  try {
    const body = (await req.json()) as { companyId?: number };
    if (!body.companyId) {
      return NextResponse.json({ error: "companyId لازم است" }, { status: 400 });
    }
    const [company] = await db
      .select()
      .from(companies)
      .where(eq(companies.id, body.companyId))
      .limit(1);
    if (!company) return NextResponse.json({ error: "شرکت یافت نشد" }, { status: 404 });

    // Reuse existing open bid for the same company
    const [existing] = await db
      .select()
      .from(bidRequests)
      .where(eq(bidRequests.companyId, company.id))
      .limit(1);
    if (existing) {
      return NextResponse.json({ ok: true, bid: existing, created: false });
    }

    const [audit] = await db
      .select()
      .from(audits)
      .where(eq(audits.companyId, company.id))
      .limit(1);
    const [proposal] = await db
      .select()
      .from(proposals)
      .where(eq(proposals.companyId, company.id))
      .limit(1);

    const token = makeToken();
    const [bid] = await db
      .insert(bidRequests)
      .values({
        companyId: company.id,
        token,
        alias: makeAlias(token),
        industry: deriveIndustry(company.name),
        snapshot: buildSnapshot(company, audit ?? null, proposal ?? null),
      })
      .returning();

    await db.insert(activityLogs).values({
      level: "info",
      message: `فراخوان قیمت‌گذاری محرمانه برای یک لید صادر شد (${bid.alias}) — هویت کارفرما پنهان است`,
    });

    return NextResponse.json({ ok: true, bid, created: true });
  } catch (err) {
    console.error("bid create error", err);
    return NextResponse.json({ error: "خطا در ساخت فراخوان" }, { status: 500 });
  }
}
