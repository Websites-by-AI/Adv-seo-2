import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { activityLogs, bidRequests, companies, quotes } from "@/db/schema";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ token: string }> };

/**
 * Award a quote → settle the platform commission → reveal the client.
 * After this, the widget page shows full company data to the winner.
 */
export async function POST(req: Request, { params }: Params) {
  try {
    const { token } = await params;
    const body = (await req.json()) as { quoteId?: number };
    if (!body.quoteId) {
      return NextResponse.json({ error: "quoteId لازم است" }, { status: 400 });
    }

    const [bid] = await db
      .select()
      .from(bidRequests)
      .where(eq(bidRequests.token, token))
      .limit(1);
    if (!bid) return NextResponse.json({ error: "فراخوان یافت نشد" }, { status: 404 });

    const bidQuotes = await db.select().from(quotes).where(eq(quotes.bidId, bid.id));
    const winner = bidQuotes.find((q) => q.id === body.quoteId);
    if (!winner) return NextResponse.json({ error: "قیمت یافت نشد" }, { status: 404 });

    for (const q of bidQuotes) {
      await db
        .update(quotes)
        .set({ status: q.id === winner.id ? "won" : "rejected" })
        .where(eq(quotes.id, q.id));
    }
    await db.update(bidRequests).set({ status: "revealed" }).where(eq(bidRequests.id, bid.id));

    const [company] = await db
      .select()
      .from(companies)
      .where(eq(companies.id, bid.companyId))
      .limit(1);

    const commissionMin = Math.round((winner.amountMin * bid.commissionPercent) / 100);
    const commissionMax = Math.round((winner.amountMax * bid.commissionPercent) / 100);

    await db.insert(activityLogs).values({
      level: "success",
      message: `پورسانت ${bid.commissionPercent}٪ تسویه شد — اطلاعات کامل لید (${bid.alias}) به «${winner.agencyName}» سپرده شد`,
    });

    return NextResponse.json({
      ok: true,
      winner: winner.agencyName,
      commission: { percent: bid.commissionPercent, min: commissionMin, max: commissionMax },
      reveal: company
        ? { name: company.name, phone: company.phone, website: company.website }
        : null,
    });
  } catch (err) {
    console.error("award error", err);
    return NextResponse.json({ error: "خطا در تسویه و واگذاری" }, { status: 500 });
  }
}
