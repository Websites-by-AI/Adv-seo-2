import { makeSampleSuppliers, ratingOf } from "@/lib/turkey";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const market = new URL(req.url).searchParams.get("market")?.trim().toLowerCase() || "restaurants";
  if (market !== "restaurants") {
    return Response.json({ ok: false, error: `Unknown market '${market}'. Supplier directory currently covers: restaurants` }, { status: 400 });
  }
  const suppliers = makeSampleSuppliers().map((s) => {
    const rating = ratingOf(s.id);
    return {
      id: s.id, market: s.market, name: s.name, regionId: s.regionId, regionFa: s.regionFa, regionTr: s.regionTr,
      phone: s.phone, deliveryZones: s.deliveryZones,
      productCount: s.products.length,
      categories: [...new Set(s.products.map((p) => p.categoryId))].sort(),
      ratingAvg: rating.avg, ratingCount: rating.count, sample: s.sample, source: s.source,
    };
  });
  return Response.json({
    ok: true, market, count: suppliers.length, suppliers,
    samplesNote: "These are educational sample suppliers with fictional +90 contacts — not real vendors.",
    disclaimer: "Listings are self-reported by suppliers; verify licenses, halal certificates and prices before contracting.",
  });
}
