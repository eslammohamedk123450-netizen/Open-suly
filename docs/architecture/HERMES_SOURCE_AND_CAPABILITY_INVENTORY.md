# Hermes source and capability inventory

**Pinned source:** NousResearch/hermes-agent  
**Revision:** `2de9f51b8008a7d49a49221c184f2f11cbfc4af1`  
**License:** MIT (upstream `LICENSE` is retained by the pinned source checkout)  
**Repository integration:** `engines/hermes/upstream` Git submodule at the exact commit above.

## Source strategy

Hermes is not copied into the FastAPI Python environment. The original upstream repository is pinned as a Git submodule, and its own Dockerfile remains the runtime build definition. This preserves the original implementation and makes the exact source inspectable in a recursive clone:

```sh
git submodule update --init --recursive engines/hermes/upstream
git -C engines/hermes/upstream rev-parse HEAD
```

The expected output is `2de9f51b8008a7d49a49221c184f2f11cbfc4af1`. A non-matching checkout is a release blocker.

## Upstream package inventory

The pinned source tree contains 28,449 Git tree entries. Top-level implementation areas include:

| Area | Upstream responsibility | SULY integration boundary |
|---|---|---|
| `agent/` | Conversation loop, context construction, memory, tool execution, providers, delegation, runtime/session lifecycle | Execute only inside one isolated task runtime; SULY remains auth, quota, approval, and audit authority |
| `gateway/` | API server, native Runs API, sessions, approvals, steering, memory/session routes, channels | Expose only the narrow task-scoped Runs API gateway; do not proxy tenant-global sessions |
| `tools/` | Terminal, browser, files, MCP, skills, delegation, and specialized tools | Default deny; per-task capability allowlist and approval |
| `skills/` and `optional-skills/` | Instruction and executable skill packages | Immutable manifest, provenance/hash/license review, explicit enablement; no automatic activation |
| `providers/` and `hermes_cli/` | Model/provider selection, CLI, configuration, persistence and setup | Keep provider secrets server-side; route via SULY policy; do not expose upstream credential stores to other engines |
| `cron/` | Scheduling and recurring agent jobs | SULY task scheduler is authoritative; translate schedules into SULY-owned tasks |
| `persistence/` | Hermes-native session and transcript storage | Per-runtime ephemeral storage unless a tenant-scoped persistence design is separately approved |
| `plugins/`, `plugin-catalog/`, `optional-mcps/` | Plugin and MCP integrations | Broker credentials and allowlist servers; never inherit host/user credentials |

The upstream tree is intentionally much larger than a single Runs API adapter. The pinned revision contains hundreds of Python modules in `agent/`, `gateway/`, `tools/`, and `cron/`, plus thousands of catalog/app/test assets. The source is now available in-repository as a pinned submodule; this does **not** mean every upstream capability has been safely activated in SULY.

## Verified API surface at the pinned revision

The source audit confirmed these native route families in `gateway/platforms/api_server.py` and `gateway/platforms/api_server_runs.py`:

- Native Runs: create, status, event stream, approval, clarify, steering, unknown resolution, stop.
- Skill and toolset metadata discovery.
- Session and memory APIs in `gateway/platforms/api_server_memory_sessions.py`.
- API server binds to port `8642` by default; `API_SERVER_HOST` and `API_SERVER_PORT` are supported environment overrides.

The API server is a powerful control surface, not a safe multi-tenant boundary by itself. Its bearer key is not a substitute for per-task whole-process isolation.

## Capability status (honest boundary)

| Capability | Upstream source present | SULY adapter status |
|---|---:|---|
| Core conversation / Runs | Yes | Native Runs adapter exists; live sandbox execution still gated |
| Approval / stop / steer | Yes | Narrow owner-scoped bridge exists; live execution not verified |
| Skills catalog | Yes | Metadata discovery only; install/update/execute not integrated |
| Tools/toolsets | Yes | Read-only catalog; invocation and task-scoped grants incomplete |
| Memory | Yes | SULY context handoff exists; durable memory bridge not implemented |
| Sessions | Yes | SULY conversations are authoritative; native session mapping not implemented |
| Subagents/delegation | Yes | Metadata visibility only; SULY child-task scheduler and budget enforcement incomplete |
| MCP | Yes | No SULY credential broker or server allowlist integration |
| Providers | Yes | No unified SULY provider gateway for Hermes |
| Cron/automation | Yes | No SULY-owned schedule adapter |
| Browser/terminal/files | Yes | Not activated; must run in a hardened task runtime with per-tool grants |

## Release gates

- Do not enable Hermes until the runtime image is digest-pinned, provisioner supports the Hermes profile, and every runtime receives an isolated process tree and private storage.
- Verify no direct egress from task containers. Current Docker networks are internal and the provisioner rejects egress opt-in without a task-aware proxy.
- Keep terminal, browser, MCP, package install, arbitrary filesystem access, and plugin execution disabled unless each has an explicit capability and approval scope.
- Run provisioner and engine adapter conformance tests against Docker in an isolated staging host.
- Verify tenant isolation, cancellation, teardown, crash recovery, quota accounting, and artifact transfer before production.
