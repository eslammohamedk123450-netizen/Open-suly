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

- A long-running polling runtime now exists in `services/api/app/worker_runtime.py`; it is opt-in via `SULY_WORKER_ENABLED=true` and is not deployed or running on a host.
- The runtime registers only the deterministic `text.analyze` operation. It does not execute arbitrary code, shell commands, browser actions, or call an AI provider.
- No live multi-worker concurrency, lease-expiry, retry-timing, or cancellation integration test has been run against a populated test task.
- The adapter revalidates the lease immediately before invoking a handler. A handler doing work longer than its lease must call `TaskWorker.renew(step)`; if renewal returns false, it must stop and must not publish side effects.
- The runtime uses one in-flight step per process, bounded polling backoff, SIGINT/SIGTERM shutdown, and server-only Supabase secret credentials. Horizontal concurrency can be added by running multiple isolated worker processes.

## Safe next step

Deploy a worker only after choosing a no-cost/approved runtime and defining the first allow-listed task handler. Until then, tasks can be planned and safely claimed through the database protocol, but they are not automatically executed.


## Database indexes
- Migration `20261119234352_task_steps_owner_index` covers the composite task-step ownership foreign key.
- Migration `20261119234405_messages_owner_index` covers the composite message ownership foreign key.
- The Supabase performance advisor no longer reports unindexed foreign keys. Unused-index notices are expected before real application traffic exists; indexes are retained for the query and FK paths they support.


## Runtime configuration
- `SULY_WORKER_ENABLED` defaults to false; API startup does not start the worker.
- `SULY_WORKER_LEASE_SECONDS` defaults to 90 (15–900).
- `SULY_WORKER_POLL_INTERVAL_SECONDS` defaults to 2 seconds (0.1–60).
- `SULY_WORKER_ID` optionally supplies a stable process identity; otherwise a process-scoped ID is generated.
- Start command: `python -m app.worker_runtime` from `services/api`.
- The only registered operation is `text.analyze`, requiring `input.operation = "text.analyze"` and a string `input.text`.
- Unknown operations fail closed and are handled by the bounded retry policy.
