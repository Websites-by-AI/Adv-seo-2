import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";

const globalForDb = globalThis as typeof globalThis & {
  __leadFairPool?: Pool;
  __leadFairDb?: ReturnType<typeof createDb>;
};

function createDb() {
  const databaseUrl = process.env.DATABASE_URL;
  if (!databaseUrl) {
    throw new Error(
      "DATABASE_URL is required. Add it to your deployment environment variables (e.g. Cloudflare project → Settings → Environment variables).",
    );
  }
  return drizzle(new Pool({ connectionString: databaseUrl }));
}

function getDb() {
  if (!globalForDb.__leadFairDb) {
    globalForDb.__leadFairDb = createDb();
  }
  return globalForDb.__leadFairDb;
}

/**
 * Lazily-initialized Drizzle client.
 *
 * The PostgreSQL connection is created on the FIRST QUERY — never at module
 * import time — so `next build` page-data collection succeeds on platforms
 * (Cloudflare, CI) where DATABASE_URL is only available at runtime.
 */
export const db = new Proxy({} as ReturnType<typeof createDb>, {
  get(_target, prop) {
    const real = getDb();
    const value = Reflect.get(real as object, prop);
    return typeof value === "function" ? value.bind(real) : value;
  },
});
