CREATE TABLE "activity_logs" (
	"id" serial PRIMARY KEY NOT NULL,
	"level" text DEFAULT 'info' NOT NULL,
	"message" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "agencies" (
	"id" serial PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"specialty" text,
	"city" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "audits" (
	"id" serial PRIMARY KEY NOT NULL,
	"company_id" integer NOT NULL,
	"url" text,
	"http_status" integer,
	"load_time_ms" integer,
	"title" text,
	"meta_description" text,
	"has_title" boolean DEFAULT false NOT NULL,
	"has_meta_description" boolean DEFAULT false NOT NULL,
	"has_h1" boolean DEFAULT false NOT NULL,
	"has_viewport" boolean DEFAULT false NOT NULL,
	"is_https" boolean DEFAULT false NOT NULL,
	"has_json_ld" boolean DEFAULT false NOT NULL,
	"has_faq_schema" boolean DEFAULT false NOT NULL,
	"word_count" integer DEFAULT 0 NOT NULL,
	"h1_count" integer DEFAULT 0 NOT NULL,
	"score" integer DEFAULT 0 NOT NULL,
	"mode" text DEFAULT 'live' NOT NULL,
	"issues" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "audits_company_id_unique" UNIQUE("company_id")
);
--> statement-breakpoint
CREATE TABLE "bid_requests" (
	"id" serial PRIMARY KEY NOT NULL,
	"company_id" integer NOT NULL,
	"token" text NOT NULL,
	"alias" text NOT NULL,
	"industry" text DEFAULT 'صنعت ساختمان' NOT NULL,
	"city" text DEFAULT 'تهران' NOT NULL,
	"status" text DEFAULT 'open' NOT NULL,
	"snapshot" jsonb NOT NULL,
	"commission_percent" integer DEFAULT 15 NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "bid_requests_token_unique" UNIQUE("token")
);
--> statement-breakpoint
CREATE TABLE "companies" (
	"id" serial PRIMARY KEY NOT NULL,
	"exhibition_id" integer,
	"name" text NOT NULL,
	"phone" text,
	"website" text,
	"source_url" text,
	"category" text,
	"google_rank" integer,
	"on_first_page" boolean,
	"rank_mode" text,
	"rank_checked_at" timestamp with time zone,
	"status" text DEFAULT 'new' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "exhibitions" (
	"id" serial PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"source_url" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "market_scans" (
	"id" serial PRIMARY KEY NOT NULL,
	"keyword" text NOT NULL,
	"mode" text DEFAULT 'live' NOT NULL,
	"engine" text DEFAULT 'google' NOT NULL,
	"results" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "proposals" (
	"id" serial PRIMARY KEY NOT NULL,
	"company_id" integer NOT NULL,
	"keyword" text NOT NULL,
	"grade" text NOT NULL,
	"summary" text NOT NULL,
	"sections" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"keywords" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"pricing" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"penalties" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"total_min" integer,
	"total_max" integer,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "proposals_company_id_unique" UNIQUE("company_id")
);
--> statement-breakpoint
CREATE TABLE "quotes" (
	"id" serial PRIMARY KEY NOT NULL,
	"bid_id" integer NOT NULL,
	"agency_id" integer,
	"agency_name" text NOT NULL,
	"amount_min" integer NOT NULL,
	"amount_max" integer NOT NULL,
	"duration_days" integer DEFAULT 90 NOT NULL,
	"note" text,
	"status" text DEFAULT 'submitted' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "audits" ADD CONSTRAINT "audits_company_id_companies_id_fk" FOREIGN KEY ("company_id") REFERENCES "public"."companies"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "bid_requests" ADD CONSTRAINT "bid_requests_company_id_companies_id_fk" FOREIGN KEY ("company_id") REFERENCES "public"."companies"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "companies" ADD CONSTRAINT "companies_exhibition_id_exhibitions_id_fk" FOREIGN KEY ("exhibition_id") REFERENCES "public"."exhibitions"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "proposals" ADD CONSTRAINT "proposals_company_id_companies_id_fk" FOREIGN KEY ("company_id") REFERENCES "public"."companies"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "quotes" ADD CONSTRAINT "quotes_bid_id_bid_requests_id_fk" FOREIGN KEY ("bid_id") REFERENCES "public"."bid_requests"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "quotes" ADD CONSTRAINT "quotes_agency_id_agencies_id_fk" FOREIGN KEY ("agency_id") REFERENCES "public"."agencies"("id") ON DELETE set null ON UPDATE no action;