import { compare } from "@/lib/turkey";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  try {
    const q = new URL(req.url).searchParams;
    const category = q.get("category") ?? q.get("q") ?? "";
    const market = q.get("market")?.trim().toLowerCase() || "restaurants";
    const region = q.get("region")?.trim() || null;
    return Response.json(compare(category, market, region));
  } catch (e) {
    return Response.json({ ok: false, error: String(e instanceof Error ? e.message : e) }, { status: 400 });
  }
}
