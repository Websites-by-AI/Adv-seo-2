import { opportunities } from "@/lib/turkey";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  try {
    const market = new URL(req.url).searchParams.get("market")?.trim().toLowerCase() || "clinics";
    return Response.json(opportunities(market));
  } catch (e) {
    return Response.json({ ok: false, error: String(e instanceof Error ? e.message : e) }, { status: 400 });
  }
}
