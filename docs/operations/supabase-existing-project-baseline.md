# Existing Supabase project baseline

**Verified:** 2026-11-20  
**Project:** SULY AI AGNIT  
**Project ref:** `razvryvazmqvvqkzetuo`  
**Region:** `eu-west-1`  
**Database:** PostgreSQL 17.11.0.011  
**Project status:** `ACTIVE_HEALTHY`

## Critical finding: this is an established, populated project

The connected Supabase project is not a blank database. It already contains application data and a substantial schema. Do not create a replacement project, reset the database, drop existing objects, or replay an assumed clean schema over it.

At verification time:

- 98 tables existed in the `public` schema.
- All 98 had Row Level Security enabled.
- 12 RLS-enabled tables had no policies. This blocks ordinary client-role access and may be intentional for internal/server-only tables; do not add policies without an access-model review.
- 183 Supabase migration-history entries existed after the private-schema bootstrap migration was applied.
- Existing product data, user records, conversations, messages, agent/task records, credit records, model/provider registry data, and HIMS-related migration history were present.
- The existing migration history includes `20261117015250 / 20261117001500_hims_activation_user_feature_lock`. HIMS is an existing core capability and must be preserved.

The repository currently contains the newly aligned private-schema bootstrap migration, not the complete historical SQL for the 182 prior migrations. Treat this as a migration-history reconciliation gap. Do not run `supabase db reset`, and do not use `supabase db push --remote` until the existing schema and historical migration sources have been reconciled and reviewed.

## Bootstrap migration applied

The following additive migration was applied to the existing project:

- Repository file: `supabase/migrations/20261119225717_suly_private_schema_bootstrap.sql`
- Database migration name: `suly_private_schema_bootstrap`
- Result: schema `suly_private` exists.
- Verification: `anon` and `authenticated` do not have `USAGE` on this schema.

This schema is reserved for future server-owned platform data. No user-facing tables or grants were added.

## Security Advisor findings

The Security Advisor reported the following findings at verification time:

| Finding | Count / level | Handling |
|---|---:|---|
| RLS enabled, no policy | 12 / INFO | Keep closed unless a documented access requirement exists. |
| Extension installed in `public` | 2 / WARN | `vector` and `pg_net`; assess safe relocation separately. |
| Public can execute SECURITY DEFINER function | 1 / WARN | `suly_get_public_conversation(uuid)`; intended public-share behavior appears possible, but share-token generation, revocation, and response scope require a dedicated review. |
| Authenticated can execute SECURITY DEFINER functions | 73 / WARN | Audit each function's authorization, ownership checks, search_path, and grants. Do not blanket-revoke or blindly switch to SECURITY INVOKER. |
| Leaked-password protection disabled | 1 / WARN | Enable through Auth security settings after reviewing the user sign-in impact. |

A focused source inspection found that:

- `cancel_agent_task_job(uuid)` checks `auth.uid()` and matches the job owner before changing a task.
- `suly_admin_adjust_credits(...)`, `suly_admin_create_activation_code(...)`, and `suly_admin_delete_provider(integer)` include administrator checks in their function bodies.
- `suly_get_public_conversation(uuid)` is executable by `anon` and `authenticated`; its share-token column is nullable and unique. Token generation and revocation behavior still need review.

These focused checks are not a complete audit of all 73 functions.

## Performance Advisor findings

The Performance Advisor reported:

- 77 unindexed foreign keys (INFO).
- 50 indexes not observed as used (INFO).
- 9 cases of multiple permissive policies for the same role/action (WARN).

Do not automatically add all suggested indexes or delete unused indexes. Review actual query patterns, table size, write cost, and policy intent before changing production schema.

## Connection and key handling

- The Supabase project-management/database connection was verified through the connected Supabase integration.
- A live read-only SQL query succeeded.
- The private-schema migration was applied and verified.
- The FastAPI runtime has not yet been launched against this project from CI or a deployed host; do not claim application-level connectivity is fully tested.
- The project has a modern publishable API key. The repository now expects `SUPABASE_PUBLISHABLE_KEY`.
- Publishable keys may be used by clients with correctly configured RLS. Secret/service-role keys must remain in a trusted server secret store and must never enter Git, Expo public variables, or mobile/web bundles.
- User-scoped backend Data API requests must forward a verified user's access token so that RLS evaluates the actual user. Never share a mutable authenticated Supabase client across requests.

Supabase is deprecating legacy `anon` and `service_role` keys by the end of 2026 in favor of publishable and secret keys. New work should use the new key types. See the official [key migration guide](https://supabase.com/docs/guides/getting-started/migrating-to-new-api-keys).

## Safe next steps

1. Reconcile the existing 182 historical migration sources with the repository without resetting or replacing the database.
2. Audit all SECURITY DEFINER functions and the 12 policy-free tables.
3. Review public conversation sharing and token lifecycle.
4. Enable leaked-password protection after reviewing Auth settings.
5. Build a request-scoped authenticated database dependency and test cross-user isolation.
6. Add integration tests against a controlled test environment before introducing new user-facing tables or RLS policies.
7. Run security and performance advisors again after each reviewed schema change.

## Verification commands

For Supabase CLI v3, hosted database inspection must explicitly use `--remote`. Hosted changes must be reviewed first and require explicit confirmation. See the [CLI v3 breaking-change notice](https://supabase.com/changelog/2026-11-04/cli-v3-local-by-default).
