import { makeSampleSuppliers, rateSupplier } from "@/lib/turkey";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  try {
    const body = await req.json().catch(() => ({}));
    const supplierId = String(body?.supplierId ?? body?.id ?? "").slice(0, 20);
    const supplier = makeSampleSuppliers().find((s) => s.id === supplierId);
    if (!supplier) {
      return Response.json({ ok: false, error: `Supplier '${supplierId || "?"}' not found. List ids via GET /api/turkey/suppliers.` }, { status: 400 });
    }
    const rating = rateSupplier(supplierId, {
      price: num(body?.price), quality: num(body?.quality),
      delivery: num(body?.delivery), satisfaction: num(body?.satisfaction),
    });
    return Response.json({ ok: true, supplierId, supplier: supplier.name, rating });
  } catch (e) {
    return Response.json({ ok: false, error: String(e instanceof Error ? e.message : e) }, { status: 400 });
  }
}

function num(v: unknown): number | undefined {
  if (v === undefined || v === null || v === "") return undefined;
  const n = Number(v);
  return Number.isNaN(n) ? undefined : n;
}
