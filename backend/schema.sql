-- Run this once in Supabase SQL Editor. Auth is handled by Supabase Auth.
create extension if not exists pgcrypto;

create table if not exists public.trips (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 160),
  destination text not null check (char_length(destination) between 1 and 120),
  start_date date not null,
  duration int not null check (duration between 1 and 21),
  preferences jsonb not null default '{}'::jsonb,
  itinerary jsonb not null default '[]'::jsonb,
  accommodations jsonb not null default '[]'::jsonb,
  transportation jsonb not null default '{}'::jsonb,
  share_code text unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Safe migration for projects that ran an earlier version of this schema.
alter table public.trips add column if not exists accommodations jsonb not null default '[]'::jsonb;
alter table public.trips add column if not exists transportation jsonb not null default '{}'::jsonb;
alter table public.trips add column if not exists share_code text unique;

-- Collaborators may edit itinerary data, but cannot transfer ownership or alter invite codes.
revoke update on public.trips from public, anon, authenticated;
grant update (name, preferences, itinerary, accommodations, transportation) on public.trips to authenticated;

create index if not exists trips_user_updated_idx on public.trips (user_id, updated_at desc);
create table if not exists public.trip_members (
  trip_id uuid not null references public.trips(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  joined_at timestamptz not null default now(),
  primary key (trip_id, user_id)
);
create index if not exists trip_members_user_idx on public.trip_members (user_id, trip_id);

-- Enforce a per-user AI budget across app instances and backend restarts.
create table if not exists public.ai_usage_limits (
  user_id uuid primary key references auth.users(id) on delete cascade,
  window_started_at timestamptz not null default now(),
  request_count integer not null default 0 check (request_count >= 0)
);
alter table public.ai_usage_limits enable row level security;
revoke all on public.ai_usage_limits from public, anon, authenticated;

create or replace function public.consume_ai_quota()
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  caller_id uuid := auth.uid();
  used_count integer;
begin
  if caller_id is null then return false; end if;
  insert into public.ai_usage_limits as existing (user_id, window_started_at, request_count)
  values (caller_id, pg_catalog.now(), 1)
  on conflict (user_id) do update set
    window_started_at = case
      when existing.window_started_at <= pg_catalog.now() - interval '1 hour' then excluded.window_started_at
      else existing.window_started_at
    end,
    request_count = case
      when existing.window_started_at <= pg_catalog.now() - interval '1 hour' then 1
      else case when existing.request_count < 11 then existing.request_count + 1 else 11 end
    end
  returning request_count into used_count;
  return used_count <= 10;
end;
$$;
revoke all on function public.consume_ai_quota() from public, anon;
grant execute on function public.consume_ai_quota() to authenticated;

alter table public.trips enable row level security;
drop policy if exists "Users can read their trips" on public.trips;
create policy "Users can read their trips" on public.trips for select to authenticated using (
  auth.uid() = user_id or exists (select 1 from public.trip_members m where m.trip_id = id and m.user_id = auth.uid())
);
drop policy if exists "Users can create their trips" on public.trips;
create policy "Users can create their trips" on public.trips for insert to authenticated with check (auth.uid() = user_id);
drop policy if exists "Users can update their trips" on public.trips;
create policy "Users can update their trips" on public.trips for update to authenticated
  using (auth.uid() = user_id or exists (select 1 from public.trip_members m where m.trip_id = id and m.user_id = auth.uid()))
  with check (auth.uid() = user_id or exists (select 1 from public.trip_members m where m.trip_id = id and m.user_id = auth.uid()));
drop policy if exists "Users can delete their trips" on public.trips;
create policy "Users can delete their trips" on public.trips for delete to authenticated using (auth.uid() = user_id);

create or replace function public.set_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end; $$;
drop trigger if exists trips_updated_at on public.trips;
create trigger trips_updated_at before update on public.trips for each row execute function public.set_updated_at();

create or replace function public.guard_trip_security_fields()
returns trigger language plpgsql as $$
begin
  if new.user_id is distinct from old.user_id then
    raise exception 'Trip ownership cannot be changed';
  end if;
  if new.share_code is distinct from old.share_code and auth.uid() is distinct from old.user_id then
    raise exception 'Only the trip owner can change its invite code';
  end if;
  return new;
end;
$$;
drop trigger if exists trips_guard_security_fields on public.trips;
create trigger trips_guard_security_fields before update on public.trips
for each row execute function public.guard_trip_security_fields();

-- Shareable trips: collaborators can view and edit only after joining via a private share code.
alter table public.trip_members enable row level security;
drop policy if exists "Members can see collaborators" on public.trip_members;
create policy "Members can see collaborators" on public.trip_members for select to authenticated using (user_id = auth.uid());

create or replace function public.join_trip_by_code(p_code text)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare found_trip uuid;
begin
  if auth.uid() is null then raise exception 'Authentication required'; end if;
  select id into found_trip from public.trips where share_code = p_code;
  if found_trip is null then return null; end if;
  insert into public.trip_members(trip_id, user_id) values(found_trip, auth.uid()) on conflict do nothing;
  return found_trip;
end;
$$;
revoke all on function public.join_trip_by_code(text) from public, anon;
grant execute on function public.join_trip_by_code(text) to authenticated;

-- Invite codes can only be created by the trip owner, not a joined collaborator.
create or replace function public.create_trip_share_code(p_trip_id uuid, p_code text)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  caller_id uuid := auth.uid();
  current_code text;
begin
  if caller_id is null then return null; end if;
  if p_code !~ '^[A-Za-z0-9_-]{12}$' then raise exception 'Invalid invite code'; end if;
  select share_code into current_code
  from public.trips
  where id = p_trip_id and user_id = caller_id
  for update;
  if not found then return null; end if;
  if current_code is null then
    update public.trips set share_code = p_code
    where id = p_trip_id and user_id = caller_id
    returning share_code into current_code;
  end if;
  return current_code;
end;
$$;
revoke all on function public.create_trip_share_code(uuid, text) from public, anon;
grant execute on function public.create_trip_share_code(uuid, text) to authenticated;

-- Enable trip record updates for Supabase Realtime when the publication is available.
do $$ begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime')
     and not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'trips') then
    alter publication supabase_realtime add table public.trips;
  end if;
end $$;
