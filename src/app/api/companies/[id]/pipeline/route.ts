import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { companies, audits, proposals, activityLogs } from "@/db/schema";
import { checkGoogleRank, auditWebsite, suggestKeywords, politeDelay } from "@/lib/pipeline";
import { generateProposal } from "@/lib/proposal";
import { normalizeUrl } from "@/lib/utils";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

async function log(level: string, message: string) {
  await db.insert(activityLogs).values({ level, message });
}

export async function POST(_req: Request, { params }: Params) {
  const { id } = await params;
  const companyId = Number(id);
  if (!Number.isFinite(companyId)) {
    return NextResponse.json({ error: "شناسه نامعتبر" }, { status: 400 });
  }

  const [company] = await db
    .select()
    .from(companies)
    .where(eq(companies.id, companyId))
    .limit(1);
  if (!company) {
    return NextResponse.json({ error: "شرکت یافت نشد" }, { status: 404 });
  }

  const steps: string[] = [];

  // ---------- 1) Google rank check ----------
  let rank = company.googleRank;
  let onFirstPage = company.onFirstPage;
  let rankMode = company.rankMode;
  let website = company.website;

  if (rank === null || company.status === "new") {
    await politeDelay();
    const r = await checkGoogleRank({ name: company.name, website });
    rank = r.position;
    onFirstPage = r.onFirstPage;
    rankMode = r.mode;
    if (!website && r.discoveredWebsite) {
      website = normalizeUrl(r.discoveredWebsite) ?? website;
    }
    steps.push(
      r.onFirstPage
        ? `«${company.name}» در صفحه اول گوگل است (رتبه ${r.position}) — لید مناسبی نیست`
        : `«${company.name}» در صفحه اول گوگل نیست (رتبه ${r.position}${r.mode === "simulated" ? "، برآورد" : ""}) — لید شکار شد`,
    );
    await db
      .update(companies)
      .set({
        googleRank: rank,
        onFirstPage,
        rankMode,
        rankCheckedAt: new Date(),
        website,
        status: "checked",
      })
      .where(eq(companies.id, companyId));
  }

  // ---------- 2) Website audit ----------
  let [audit] = await db
    .select()
    .from(audits)
    .where(eq(audits.companyId, companyId))
    .limit(1);

  if (!audit) {
    await politeDelay();
    const a = await auditWebsite(website, company.name);
    const [inserted] = await db
      .insert(audits)
      .values({ companyId, ...a })
      .onConflictDoUpdate({
        target: audits.companyId,
        set: { ...a, createdAt: new Date() },
      })
      .returning();
    audit = inserted;
    steps.push(
      a.mode === "no-site"
        ? `وب‌سایتی برای «${company.name}» پیدا نشد — بزرگ‌ترین فرصت فروش`
        : a.mode === "unreachable"
          ? `وب‌سایت «${company.name}» در دسترس نیست — فرصت بازسازی`
          : `ممیزی وب‌سایت «${company.name}» کامل شد — امتیاز ${a.score} از ۱۰۰ با ${a.issues.length} مشکل`,
    );
    await db
      .update(companies)
      .set({ status: "audited" })
      .where(eq(companies.id, companyId));
  }

  // ---------- 3) Proposal generation ----------
  let [proposal] = await db
    .select()
    .from(proposals)
    .where(eq(proposals.companyId, companyId))
    .limit(1);

  const isLead = onFirstPage === false;
  if (!proposal && isLead && audit) {
    const keywords = suggestKeywords(company);
    const p = generateProposal(
      { ...company, googleRank: rank, onFirstPage, rankMode, website },
      audit,
      keywords,
    );
    const [inserted] = await db
      .insert(proposals)
      .values({ companyId, ...p })
      .onConflictDoUpdate({
        target: proposals.companyId,
        set: { ...p, createdAt: new Date() },
      })
      .returning();
    proposal = inserted;
    steps.push(`پیشنهادنامه سئو برای «${company.name}» آماده ارسال شد`);
    await db
      .update(companies)
      .set({ status: "proposal_ready" })
      .where(eq(companies.id, companyId));
    await log("success", `پیشنهادنامه «${company.name}» صادر شد — اولویت ${p.grade}`);
  } else if (!isLead && !proposal) {
    steps.push("این شرکت در صفحه اول است؛ پیشنهادنامه صادر نمی‌شود");
  }

  for (const s of steps) {
    if (!s.startsWith("پیشنهادنامه")) await log(s.includes("شکار") || s.includes("کامل") ? "success" : "info", s);
  }

  const [fresh] = await db
    .select({ company: companies, audit: audits, proposalId: proposals.id })
    .from(companies)
    .leftJoin(audits, eq(audits.companyId, companyId))
    .leftJoin(proposals, eq(proposals.companyId, companyId))
    .where(eq(companies.id, companyId))
    .limit(1);

  return NextResponse.json({ ok: true, steps, ...fresh });
}
