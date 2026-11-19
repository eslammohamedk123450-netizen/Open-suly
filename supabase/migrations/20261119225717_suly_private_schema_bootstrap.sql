-- Initial private namespace for future server-owned platform tables.
-- This migration was applied to the existing SULY Supabase project.
-- User-facing schemas, grants, and RLS policies are introduced in M2.
begin;

create schema if not exists suly_private;

revoke all on schema suly_private from public;
revoke all on schema suly_private from anon, authenticated;

comment on schema suly_private is
  'Server-owned SULY platform data. No client role receives access by default.';

commit;
