import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { companies, audits, proposals } from "@/db/schema";
import { generateProposal } from "@/lib/proposal";
import { normalizeUrl } from "@/lib/utils";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: Request, { params }: Params) {
  const { id } = await params;
  const companyId = Number(id);
  const rows = await db
    .select({ company: companies, audit: audits, proposal: proposals })
    .from(companies)
    .leftJoin(audits, eq(audits.companyId, companyId))
    .leftJoin(proposals, eq(proposals.companyId, companyId))
    .where(eq(companies.id, companyId))
    .limit(1);
  if (rows.length === 0) {
    return NextResponse.json({ error: "یافت نشد" }, { status: 404 });
  }
  const row = rows[0];

  // Backfill: regenerate proposals created before the pricing engine existed
  if (row.proposal && row.proposal.pricing.length === 0) {
    const regenerated = generateProposal(row.company, row.audit, row.proposal.keywords);
    const [updated] = await db
      .update(proposals)
      .set(regenerated)
      .where(eq(proposals.id, row.proposal.id))
      .returning();
    row.proposal = updated;
  }

  return NextResponse.json(row);
}

export async function PATCH(req: Request, { params }: Params) {
  const { id } = await params;
  const companyId = Number(id);
  const body = (await req.json()) as { website?: string; name?: string; phone?: string };
  const patch: Partial<typeof companies.$inferInsert> = {};
  if (typeof body.website === "string") {
    patch.website = body.website.trim() ? normalizeUrl(body.website) : null;
  }
  if (typeof body.name === "string" && body.name.trim()) patch.name = body.name.trim();
  if (typeof body.phone === "string") patch.phone = body.phone.trim() || null;

  const [updated] = await db
    .update(companies)
    .set(patch)
    .where(eq(companies.id, companyId))
    .returning();
  if (!updated) return NextResponse.json({ error: "یافت نشد" }, { status: 404 });

  // Website change invalidates audit & proposal
  if (patch.website !== undefined) {
    await db.delete(audits).where(eq(audits.companyId, companyId));
    await db.delete(proposals).where(eq(proposals.companyId, companyId));
    await db
      .update(companies)
      .set({ status: "checked" })
      .where(eq(companies.id, companyId));
  }
  return NextResponse.json({ ok: true, company: updated });
}

export async function DELETE(_req: Request, { params }: Params) {
  const { id } = await params;
  const companyId = Number(id);
  await db.delete(companies).where(eq(companies.id, companyId));
  return NextResponse.json({ ok: true });
}
