-- Persist the exact validated skill bytes so an approved package can be
-- mounted into its owner-scoped Hermes runtime and re-hashed before use.
alter table public.hermes_skill_approvals
  add column if not exists content_utf8 text;

alter table public.hermes_skill_approvals
  drop constraint if exists hermes_skill_content_utf8_size_check;

alter table public.hermes_skill_approvals
  add constraint hermes_skill_content_utf8_size_check
  check (
    content_utf8 is null
    or (
      octet_length(content_utf8) = content_bytes
      and octet_length(content_utf8) between 1 and 262144
    )
  );

comment on column public.hermes_skill_approvals.content_utf8 is
  'Exact UTF-8 skill package bytes stored as inert text. Application verifies SHA-256 before mounting; never execute from the database.';
