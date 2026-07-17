import { NextResponse } from "next/server";
import { desc, eq } from "drizzle-orm";
import { db } from "@/db";
import { companies, marketScans, proposals, activityLogs, type SerpEntry } from "@/db/schema";
import { scanSerp, matchExhibitorPosition, type ExhibitorLite } from "@/lib/serp";

export const dynamic = "force-dynamic";

interface MatchResult {
  companyId: number;
  name: string;
  website: string | null;
  googleRank: number | null;
  position: number | null;
  hasProposal: boolean;
  status: string;
}

async function buildComparison(scan: {
  id: number;
  keyword: string;
  mode: string;
  engine: string;
  results: SerpEntry[];
  createdAt: Date;
}) {
  const exhibitors = await db
    .select({
      id: companies.id,
      name: companies.name,
      website: companies.website,
      googleRank: companies.googleRank,
      status: companies.status,
      proposalId: proposals.id,
    })
    .from(companies)
    .leftJoin(proposals, eq(proposals.companyId, companies.id))
    .limit(300);

  const matches: MatchResult[] = exhibitors.map((ex) => ({
    companyId: ex.id,
    name: ex.name,
    website: ex.website,
    googleRank: ex.googleRank,
    position: matchExhibitorPosition(ex as ExhibitorLite, scan.results),
    hasProposal: ex.proposalId !== null,
    status: ex.status,
  }));

  // Annotate SERP entries with matched exhibitor (domain/fuzzy), keeping any
  // simulation-time annotation.
  const annotated = scan.results.map((e) => {
    const m = matches.find((mm) => mm.position === e.position);
    return {
      ...e,
      matchedCompanyId: m?.companyId ?? e.matchedCompanyId ?? null,
      matchedCompanyName: m?.name ?? e.matchedCompanyName ?? null,
    };
  });

  const present = matches.filter((m) => m.position !== null);
  const absent = matches.filter((m) => m.position === null);

  return {
    scan: { ...scan, results: annotated },
    present,
    absent,
    summary: {
      exhibitorsTotal: matches.length,
      visibleInTop10: present.length,
      invisible: absent.length,
      visibilityRate:
        matches.length > 0 ? Math.round((present.length / matches.length) * 100) : 0,
      outsidersInTop10: annotated.filter((e) => !e.matchedCompanyId).length,
    },
  };
}

export async function GET() {
  const [latest] = await db
    .select()
    .from(marketScans)
    .orderBy(desc(marketScans.id))
    .limit(1);
  const history = await db
    .select({ id: marketScans.id, keyword: marketScans.keyword, mode: marketScans.mode, engine: marketScans.engine, createdAt: marketScans.createdAt })
    .from(marketScans)
    .orderBy(desc(marketScans.id))
    .limit(8);

  if (!latest) return NextResponse.json({ comparison: null, history });
  return NextResponse.json({ comparison: await buildComparison(latest), history });
}

export async function POST(req: Request) {
  try {
    const body = (await req.json()) as { keyword?: string };
    const keyword = body.keyword?.trim();
    if (!keyword || keyword.length < 2) {
      return NextResponse.json({ error: "کلمه کلیدی را وارد کنید" }, { status: 400 });
    }

    const exhibitors = await db
      .select({
        id: companies.id,
        name: companies.name,
        website: companies.website,
        googleRank: companies.googleRank,
      })
      .from(companies)
      .limit(300);

    const { entries, mode, engine } = await scanSerp(keyword, exhibitors);

    const [scan] = await db
      .insert(marketScans)
      .values({ keyword, mode, engine, results: entries })
      .returning();

    await db.insert(activityLogs).values({
      level: mode === "live" ? "success" : "warn",
      message: `اسکن گوگل برای «${keyword}» انجام شد — ${entries.length} نتیجه صفحه اول${mode === "simulated" ? " (داده برآوردی)" : ` از ${engine}`}`,
    });

    return NextResponse.json({ ok: true, comparison: await buildComparison(scan) });
  } catch (err) {
    console.error("serp scan error", err);
    return NextResponse.json({ error: "خطا در اسکن گوگل" }, { status: 500 });
  }
}
