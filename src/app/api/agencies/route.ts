import { NextResponse } from "next/server";
import { db } from "@/db";
import { agencies } from "@/db/schema";
import { AGENCY_SEED } from "@/lib/bids";

export const dynamic = "force-dynamic";

export async function GET() {
  // Auto-seed the Iranian SEO agency directory once
  const existing = await db.select().from(agencies).limit(1);
  if (existing.length === 0) {
    await db.insert(agencies).values(AGENCY_SEED);
  }
  const list = await db.select().from(agencies);
  return NextResponse.json({ agencies: list });
}
