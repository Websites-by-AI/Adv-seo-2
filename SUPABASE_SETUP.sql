-- Run in Supabase SQL Editor.
-- Safe for a new installation and additive for the earlier clinic_leads schema.
create extension if not exists pgcrypto;

create table if not exists public.clinic_leads (
  id uuid primary key default gen_random_uuid(),
  dedupe_key text not null unique,
  name text not null,
  website text default '',
  phone text default '',
  email text default '',
  whatsapp text default '',
  tags jsonb default '[]'::jsonb,
  address text default '',
  specialty text default '',
  source text default '',
  result_type text default 'candidate',
  status text default 'new',
  seo_score integer default 0 check (seo_score between 0 and 100),
  opportunity_score integer default 0 check (opportunity_score between 0 and 100),
  raw jsonb default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Upgrade an older table that used website as the only unique key.
alter table public.clinic_leads add column if not exists dedupe_key text;
alter table public.clinic_leads add column if not exists email text default '';
alter table public.clinic_leads add column if not exists whatsapp text default '';
alter table public.clinic_leads add column if not exists tags jsonb default '[]'::jsonb;
alter table public.clinic_leads alter column website drop not null;
alter table public.clinic_leads alter column website set default '';

update public.clinic_leads
set dedupe_key = case
  when coalesce(trim(website), '') <> '' then
    'website:' || lower(regexp_replace(regexp_replace(trim(website), '^https?://(www\.)?', '', 'i'), '/.*$', ''))
  else
    'entity:' || encode(digest(lower(
      coalesce(name, '') || '|' || coalesce(phone, '') || '|' ||
      coalesce(address, '') || '|' || coalesce(source, '')
    ), 'sha256'), 'hex')
end
where dedupe_key is null or dedupe_key = '';

alter table public.clinic_leads alter column dedupe_key set not null;
alter table public.clinic_leads drop constraint if exists clinic_leads_website_key;
create unique index if not exists clinic_leads_dedupe_key_uidx on public.clinic_leads(dedupe_key);
create index if not exists clinic_leads_website_idx on public.clinic_leads(website) where website <> '';
create index if not exists clinic_leads_phone_idx on public.clinic_leads(phone) where phone <> '';
create index if not exists clinic_leads_email_idx on public.clinic_leads(email) where email <> '';
create index if not exists clinic_leads_tags_gin_idx on public.clinic_leads using gin(tags);
create index if not exists clinic_leads_status_idx on public.clinic_leads(status);
create index if not exists clinic_leads_specialty_idx on public.clinic_leads(specialty);
create index if not exists clinic_leads_created_at_idx on public.clinic_leads(created_at desc);

create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists clinic_leads_updated_at on public.clinic_leads;
create trigger clinic_leads_updated_at
before update on public.clinic_leads
for each row execute function public.set_updated_at();

-- Keep RLS enabled. The server uses the service-role key; never expose it in browser code.
alter table public.clinic_leads enable row level security;
