# SULY worker runtime boundary

## Implemented

- PostgreSQL atomically claims one dependency-ready step with `FOR UPDATE SKIP LOCKED`.
- Each claim increments the attempt counter and returns an opaque lease token with an expiry.
- Lease renewal, checkpoint completion, and failure/retry all compare the current token and expiry.
- Retry scheduling uses bounded exponential backoff; attempts are bounded by each step's `max_attempts`.
- Expired leases are reclaimed or terminally failed. Task cancellation revokes outstanding leases and prevents further claims.
- All four RPC functions are SECURITY INVOKER and executable only by `service_role`; authenticated clients cannot invoke them.
- `services/api/app/services/task_worker.py` provides a one-step worker adapter. It requires a server-side Supabase client and an allow-listed handler supplied by the hosting process.

## Not deployed / not yet proven

- No long-running worker process or hosting target is configured.
- No provider/tool handlers are registered. The adapter does not execute arbitrary code or call an AI provider.
- No live multi-worker concurrency, lease-expiry, retry-timing, or cancellation integration test has been run against a populated test task.
- The adapter revalidates the lease immediately before invoking a handler. A handler doing work longer than its lease must call `TaskWorker.renew(step)`; if renewal returns false, it must stop and must not publish side effects.
- A production worker must use a stable unique worker ID, bounded concurrency, process shutdown handling, and server-only Supabase secret credentials.

## Safe next step

Deploy a worker only after choosing a no-cost/approved runtime and defining the first allow-listed task handler. Until then, tasks can be planned and safely claimed through the database protocol, but they are not automatically executed.


## Database indexes
- Migration `20261119234352_task_steps_owner_index` covers the composite task-step ownership foreign key.
- Migration `20261119234405_messages_owner_index` covers the composite message ownership foreign key.
- The Supabase performance advisor no longer reports unindexed foreign keys. Unused-index notices are expected before real application traffic exists; indexes are retained for the query and FK paths they support.
