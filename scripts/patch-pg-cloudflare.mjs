/**
 * Fix pg-cloudflare for Cloudflare Workers deployments.
 *
 * pg-cloudflare's `exports` map resolves to a stub (`dist/empty.js`) outside
 * the `workerd` condition. Next.js's file tracer (nft) runs with plain Node
 * conditions, so it only traces the stub — and the OpenNext bundler (which
 * DOES use the `workerd` condition) then fails with:
 *   "The module ./dist/index.js was not found on the file system"
 *
 * This script rewrites the exports map so the real workerd implementation is
 * traced and bundled. It is safe locally: `pg` only requires pg-cloudflare
 * when it detects a Workers runtime (navigator.userAgent contains "workers"),
 * so Node.js development never loads the cloudflare:sockets code path.
 *
 * Cloudflare build command:
 *   node scripts/patch-pg-cloudflare.mjs && npx opennextjs-cloudflare build
 */
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const pkgPath = join(process.cwd(), "node_modules", "pg-cloudflare", "package.json");

if (!existsSync(pkgPath)) {
  console.warn("[patch-pg-cloudflare] pg-cloudflare not installed — skipping");
  process.exit(0);
}

const pkg = JSON.parse(readFileSync(pkgPath, "utf8"));
const alreadyPatched = pkg.exports?.["."]?.default === "./dist/index.js";

if (alreadyPatched) {
  console.log("[patch-pg-cloudflare] already patched");
  process.exit(0);
}

pkg.exports = {
  ".": {
    workerd: {
      import: "./esm/index.mjs",
      require: "./dist/index.js",
    },
    import: "./esm/index.mjs",
    require: "./dist/index.js",
    default: "./dist/index.js",
  },
  "./package.json": "./package.json",
};

writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + "\n");
console.log("[patch-pg-cloudflare] exports patched → workerd implementation will be traced");
