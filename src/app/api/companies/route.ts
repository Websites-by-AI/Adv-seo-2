import { NextResponse } from "next/server";
import { desc, eq, sql } from "drizzle-orm";
import { db } from "@/db";
import { companies, audits, proposals, activityLogs } from "@/db/schema";

export const dynamic = "force-dynamic";

export async function GET() {
  const rows = await db
    .select({
      company: companies,
      audit: audits,
      proposalId: proposals.id,
    })
    .from(companies)
    .leftJoin(audits, eq(audits.companyId, companies.id))
    .leftJoin(proposals, eq(proposals.companyId, companies.id))
    .orderBy(desc(companies.id))
    .limit(500);

  const list = rows.map((r) => ({
    ...r.company,
    audit: r.audit,
    proposalId: r.proposalId,
  }));

  const stats = {
    total: list.length,
    checked: list.filter((c) => c.googleRank !== null).length,
    leads: list.filter((c) => c.onFirstPage === false).length,
    onFirstPage: list.filter((c) => c.onFirstPage === true).length,
    noWebsite: list.filter((c) => !c.website && c.status !== "new").length,
    proposalsReady: list.filter((c) => c.proposalId !== null).length,
    avgScore:
      list.filter((c) => c.audit && c.audit.mode === "live").length > 0
        ? Math.round(
            list
              .filter((c) => c.audit && c.audit.mode === "live")
              .reduce((s, c) => s + (c.audit?.score ?? 0), 0) /
              list.filter((c) => c.audit && c.audit.mode === "live").length,
          )
        : null,
  };

  return NextResponse.json({ companies: list, stats });
}

export async function DELETE() {
  await db.delete(companies);
  await db
    .delete(activityLogs)
    .where(sql`true`);
  await db.insert(activityLogs).values({
    level: "warn",
    message: "پایگاه داده لیدها پاک‌سازی شد",
  });
  return NextResponse.json({ ok: true });
}
