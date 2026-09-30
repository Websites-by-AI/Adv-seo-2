import { smartPlan } from "@/lib/turkey";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  try {
    const body = await req.json().catch(() => ({}));
    return Response.json(smartPlan(body ?? {}));
  } catch (e) {
    return Response.json({ ok: false, error: String(e instanceof Error ? e.message : e) }, { status: 400 });
  }
}
