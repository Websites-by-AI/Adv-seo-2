import { NextResponse } from "next/server";
import { desc } from "drizzle-orm";
import { db } from "@/db";
import { activityLogs } from "@/db/schema";

export const dynamic = "force-dynamic";

export async function GET() {
  const logs = await db
    .select()
    .from(activityLogs)
    .orderBy(desc(activityLogs.id))
    .limit(60);
  return NextResponse.json({ logs });
}
