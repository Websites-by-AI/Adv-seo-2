import {
  pgTable,
  serial,
  integer,
  text,
  boolean,
  timestamp,
  jsonb,
} from "drizzle-orm/pg-core";

export const exhibitions = pgTable("exhibitions", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  sourceUrl: text("source_url"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export const companies = pgTable("companies", {
  id: serial("id").primaryKey(),
  exhibitionId: integer("exhibition_id").references(() => exhibitions.id, {
    onDelete: "set null",
  }),
  name: text("name").notNull(),
  phone: text("phone"),
  website: text("website"),
  sourceUrl: text("source_url"),
  category: text("category"),
  googleRank: integer("google_rank"),
  onFirstPage: boolean("on_first_page"),
  rankMode: text("rank_mode"), // 'live' | 'simulated'
  rankCheckedAt: timestamp("rank_checked_at", { withTimezone: true }),
  status: text("status").notNull().default("new"), // new | checked | audited | proposal_ready
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export type Company = typeof companies.$inferSelect;

export const audits = pgTable("audits", {
  id: serial("id").primaryKey(),
  companyId: integer("company_id")
    .references(() => companies.id, { onDelete: "cascade" })
    .notNull()
    .unique(),
  url: text("url"),
  httpStatus: integer("http_status"),
  loadTimeMs: integer("load_time_ms"),
  title: text("title"),
  metaDescription: text("meta_description"),
  hasTitle: boolean("has_title").notNull().default(false),
  hasMetaDescription: boolean("has_meta_description")
    .notNull()
    .default(false),
  hasH1: boolean("has_h1").notNull().default(false),
  hasViewport: boolean("has_viewport").notNull().default(false),
  isHttps: boolean("is_https").notNull().default(false),
  hasJsonLd: boolean("has_json_ld").notNull().default(false),
  hasFaqSchema: boolean("has_faq_schema").notNull().default(false),
  wordCount: integer("word_count").notNull().default(0),
  h1Count: integer("h1_count").notNull().default(0),
  score: integer("score").notNull().default(0),
  mode: text("mode").notNull().default("live"), // live | no-site | unreachable
  issues: jsonb("issues").$type<string[]>().notNull().default([]),
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export type Audit = typeof audits.$inferSelect;

export interface ProposalSection {
  heading: string;
  body: string;
  bullets?: string[];
}

/** One priced line item of the SEO package (amounts in Toman). */
export interface PricingItem {
  title: string;
  details: string;
  costMin: number;
  costMax: number;
}

/** One black-hat practice that Google penalizes. */
export interface PenaltyItem {
  title: string;
  consequence: string;
}

export const proposals = pgTable("proposals", {
  id: serial("id").primaryKey(),
  companyId: integer("company_id")
    .references(() => companies.id, { onDelete: "cascade" })
    .notNull()
    .unique(),
  keyword: text("keyword").notNull(),
  grade: text("grade").notNull(), // A | B | C (priority)
  summary: text("summary").notNull(),
  sections: jsonb("sections").$type<ProposalSection[]>().notNull().default([]),
  keywords: jsonb("keywords").$type<string[]>().notNull().default([]),
  pricing: jsonb("pricing").$type<PricingItem[]>().notNull().default([]),
  penalties: jsonb("penalties").$type<PenaltyItem[]>().notNull().default([]),
  totalMin: integer("total_min"),
  totalMax: integer("total_max"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export type Proposal = typeof proposals.$inferSelect;

export interface SerpEntry {
  position: number;
  title: string;
  url: string;
  domain: string;
  snippet: string | null;
  fromExhibitor?: boolean;
  matchedCompanyId?: number | null;
  matchedCompanyName?: string | null;
}

export const marketScans = pgTable("market_scans", {
  id: serial("id").primaryKey(),
  keyword: text("keyword").notNull(),
  mode: text("mode").notNull().default("live"), // live | simulated
  engine: text("engine").notNull().default("google"), // google | duckduckgo | bing | simulated
  results: jsonb("results").$type<SerpEntry[]>().notNull().default([]),
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export type MarketScan = typeof marketScans.$inferSelect;

/* ---------- Blind tender marketplace (confidential price bidding) ---------- */

export const agencies = pgTable("agencies", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  specialty: text("specialty"),
  city: text("city"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export interface BidSnapshot {
  googleRank: number | null;
  score: number | null;
  issuesCount: number;
  packageItems: { title: string; costMin: number; costMax: number }[];
  totalMin: number;
  totalMax: number;
  grade: string;
}

export const bidRequests = pgTable("bid_requests", {
  id: serial("id").primaryKey(),
  companyId: integer("company_id")
    .references(() => companies.id, { onDelete: "cascade" })
    .notNull(),
  token: text("token").notNull().unique(),
  alias: text("alias").notNull(),
  industry: text("industry").notNull().default("صنعت ساختمان"),
  city: text("city").notNull().default("تهران"),
  status: text("status").notNull().default("open"), // open | revealed
  snapshot: jsonb("snapshot").$type<BidSnapshot>().notNull(),
  commissionPercent: integer("commission_percent").notNull().default(15),
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export type BidRequest = typeof bidRequests.$inferSelect;

export const quotes = pgTable("quotes", {
  id: serial("id").primaryKey(),
  bidId: integer("bid_id")
    .references(() => bidRequests.id, { onDelete: "cascade" })
    .notNull(),
  agencyId: integer("agency_id").references(() => agencies.id, {
    onDelete: "set null",
  }),
  agencyName: text("agency_name").notNull(),
  amountMin: integer("amount_min").notNull(),
  amountMax: integer("amount_max").notNull(),
  durationDays: integer("duration_days").notNull().default(90),
  note: text("note"),
  status: text("status").notNull().default("submitted"), // submitted | won | rejected
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
});

export type Quote = typeof quotes.$inferSelect;

export const activityLogs = pgTable("activity_logs", {
  id: serial("id").primaryKey(),
  level: text("level").notNull().default("info"), // info | success | warn | error
  message: text("message").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true })
    .defaultNow()
    .notNull(),
});
