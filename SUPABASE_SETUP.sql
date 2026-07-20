-- Run in Supabase SQL Editor.
create extension if not exists pgcrypto;

create table if not exists public.clinic_leads (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  website text not null unique,
  phone text default '',
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
