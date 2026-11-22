-- Owner-scoped approval ledger for immutable Hermes skill packages.
-- The engine can read only packages approved by the owning SULY user.
create table if not exists public.hermes_skill_approvals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  source_revision text not null,
  license_id text not null,
  content_sha256 text not null,
  content_bytes integer not null,
  status text not null default 'pending',
  enabled boolean not null default false,
  approved_by uuid references auth.users(id) on delete set null,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint hermes_skill_name_check check (name ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$'),
  constraint hermes_skill_revision_check check (source_revision ~ '^[0-9a-f]{40}$'),
  constraint hermes_skill_license_check check (license_id in ('MIT','Apache-2.0','BSD-2-Clause','BSD-3-Clause','ISC')),
  constraint hermes_skill_digest_check check (content_sha256 ~ '^[0-9a-f]{64}$'),
  constraint hermes_skill_bytes_check check (content_bytes between 1 and 262144),
  constraint hermes_skill_status_check check (status in ('pending','approved','revoked')),
  constraint hermes_skill_activation_check check (
    (status = 'approved' and enabled = true and approved_by is not null and approved_at is not null)
    or (status <> 'approved' and enabled = false)
  ),
  constraint hermes_skill_owner_name_digest_unique unique (user_id,name,content_sha256)
);

create index if not exists hermes_skill_active_owner_idx
  on public.hermes_skill_approvals(user_id, approved_at desc)
  where status = 'approved' and enabled = true;

alter table public.hermes_skill_approvals enable row level security;
revoke all on table public.hermes_skill_approvals from public, anon, authenticated;
grant select on table public.hermes_skill_approvals to authenticated;
grant all on table public.hermes_skill_approvals to service_role;

drop policy if exists hermes_skill_owner_select on public.hermes_skill_approvals;
create policy hermes_skill_owner_select on public.hermes_skill_approvals
  for select to authenticated using (auth.uid() = user_id);

comment on table public.hermes_skill_approvals is
  'SULY-owned immutable Hermes skill package approval ledger. Skill bytes are mounted only after digest and owner approval checks.';
