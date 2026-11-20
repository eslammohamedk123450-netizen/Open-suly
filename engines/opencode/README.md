# OpenCode upstream engine

This directory pins the **complete upstream OpenCode repository** as a Git submodule at `upstream/`. The source is not reimplemented or flattened into SULY's FastAPI process.

## Provenance

- Upstream: https://github.com/anomalyco/opencode
- Pinned commit: `4cca18d80450a3dd6a9a4142028bde84ccb3116e`
- Upstream package version at the audited revision: `2.3.0`
- License: MIT (the original `LICENSE` is retained in the submodule)
- Upstream commit signature: verified by GitHub at import time
- Pin rationale: this is the immutable revision already reviewed in `docs/architecture/OPENCODE_INTEGRATION_AUDIT.md`. Do not silently advance to the moving `dev` branch.

## Get the original source

From the SULY repository root:

```bash
git submodule update --init --recursive engines/opencode/upstream
```

Verify the pin:

```bash
git -C engines/opencode/upstream rev-parse HEAD
```

It must equal the commit above. The submodule contains the original monorepo, including its server, core, AI/provider integrations, CLI, protocol/schema, plugin system, browser plugin, TUI, skills, tests, build scripts, and original documentation.

## Runtime boundary

The source import is a **source-inclusion milestone**, not a claim that OpenCode is already serving SULY users. The upstream server has a broad filesystem, shell, PTY, MCP, plugin, and credential surface. It must remain disabled until SULY provisions a separate per-task-attempt sandbox and broker.

SULY remains authoritative for user identity, tenant ownership, task/lease state, approvals, audit, usage, and secrets. Never pass Supabase service credentials or arbitrary host paths into OpenCode. Do not expose the upstream server directly to the mobile/web client.

## Build/runtime notes

The pinned upstream monorepo uses Bun (declared as `bun@1.4.4`) and a workspace of packages. Its server package depends on other upstream workspace packages, so copying only `packages/server` is not a complete engine. Build and run it from the upstream repository root using its own lockfile and workspace scripts, in a dedicated image.

The upstream repository is large. Keep submodule checkout out of the normal SULY client/API CI path; build the engine in its own job/image when the sandbox implementation is ready.

## Update policy

Any upstream update requires:
1. Review the new commit and security advisories.
2. Re-run license and dependency review.
3. Update the gitlink pin and `UPSTREAM.json` together.
4. Re-run adapter, isolation, and engine smoke tests.


## SULY HTTP bridge checkpoint

- `services/api/app/services/opencode_http.py` is a narrow async HTTP transport for one already-validated task-attempt runtime lease.
- It uses HTTPS only, Basic auth in the Authorization header, TLS verification, no environment proxy inheritance, no redirects, bounded timeouts/connections/response size, and a small explicit route allowlist.
- Initial operations are health, create-session (with catch-all ask permissions), and bounded skill/provider catalog metadata. It deliberately does not expose prompt execution, shell, PTY, MCP, plugins, filesystem APIs, arbitrary paths, or session deletion.
- This is not a runtime provisioner and does not make OpenCode available to users. The engine remains disabled until durable session ownership, worker/lease checks, permission UI, safe prompt/output reduction, and a concrete isolated runtime provider are implemented.
