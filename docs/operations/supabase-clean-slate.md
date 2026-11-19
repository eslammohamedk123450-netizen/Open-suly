# Supabase clean-slate record

**Project:** SULY  
**Project ref:** `razvryvazmqvvqkzetuo`  
**Region:** `eu-west-1`  
**PostgreSQL:** 17.11

## Reset completed

The previous application-owned public schema was removed. The database now starts from a clean application schema for the standalone SULY product.

Verified after reset:
- `public` contains no legacy tables or functions before the new identity migration.
- All 8 previous Auth accounts were deleted; Auth now contains zero users.
- All 27 previous Vault credentials were deleted.
- All previous scheduled application cron jobs were removed.
- The old `suly_private` schema was removed.
- The old `pg_net` extension was removed.
- `vector` was moved from the exposed `public` schema to `extensions` for future agent-memory needs.
- Supabase-managed schemas such as `auth`, `storage`, `realtime`, `vault`, and `supabase_migrations` were retained.

## First new application migration

`20261119231023_suly_identity_foundation.sql` creates only:
- `public.profiles`, linked to `auth.users`.
- Owner-only read/update RLS policies.
- A minimal Auth user-created trigger that creates a profile.

No old tables, RPCs, credit balances, provider catalog, HIMS objects, or legacy feature flags are carried forward.

## Storage cleanup limitation

The existing private bucket `suly-media` was retained for reuse by the new SULY product. It currently contains one 146-byte private object from the previous implementation. The connected database tools do not provide the Supabase Storage API operation required to delete the physical object safely. It must be removed through the Storage API before the bucket can be considered fully empty. Do not delete rows directly from `storage.objects`; that can orphan the physical object.

## Operational rules

- Do not run old migration files or recreate the old schema.
- New schema changes must be committed as forward migrations.
- Keep Supabase-managed schemas intact.
- Keep provider credentials empty until the new provider gateway is designed.
- Configure only the Auth providers and redirect URLs needed by the new product.
- Keep the official SULY domain and branding in the hosting/domain configuration; database reset does not alter domain ownership or DNS.
