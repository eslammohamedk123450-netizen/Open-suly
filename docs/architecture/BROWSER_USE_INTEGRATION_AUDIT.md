# Browser Use integration and isolation audit

Audit date: 2026-11-20

## Source identity

- Upstream repository: `browser-use/browser-use`
- Immutable revision: `ccbdb8095fbaf903c748880a600054a34c7b6191`
- Package version: `browser-use` 1.0.6
- License: MIT (root LICENSE and package metadata inspected)
- The MCP server is part of the package; `mcp` is a pinned core dependency.
- This audit does not copy or modify upstream source.

## Findings from the pinned source

### The MCP server executes Python inside its own process

- `browser_use/mcp/cli_mcp.py` exposes the `browser_exec` tool backed by a persistent Python REPL.
- The upstream guide explicitly states that code runs in the MCP server process and can read that process's environment and files, including `BROWSER_USE_API_KEY` when configured.
- The server imports process, filesystem, subprocess, browser-harness, authentication, and browser-control modules. It is not a narrow browser-only RPC surface.
- A shared MCP server would therefore expose its process environment, mounted files, and browser control to every connected task. Hiding the CDP URL or browser ID does not create a tenant boundary.

### Browser profiles and domain controls require care

- `browser_use/browser/browser.py` supports cloud browser, fresh local Chromium profiles, and attaching to an existing Chrome profile via the browser-harness daemon.
- `browser_use/browser/local.py` discovers local browser profiles and can create temporary profile copies. SULY must not allow a task to attach to a host user's existing Chrome or copy a real profile.
- The MCP server documents that `allowed_domains` / `prohibited_domains` apply only to its own local Chromium; they do not constrain a cloud browser. The source explicitly warns that a cloud browser could open any site.
- Therefore browser-level domain settings are not an egress security boundary. URL checks alone are also insufficient against redirects, DNS rebinding, private IPs, IPv6, alternate ports, and browser subresources.

### Browser lifecycle is process-coupled

- The MCP server starts and stops cloud browser daemons and includes cleanup/reaper behavior when the server exits.
- Browser sessions and the persistent REPL belong to one server process. Reusing one server across tasks would share execution context and browser state.

## Required SULY integration design

Browser Use remains disabled until all of the following are implemented and tested:

1. One isolated MCP server process/container per task attempt, with its own ephemeral filesystem, Python environment, browser profile, and credentials.
2. Non-root runtime, read-only base filesystem, one bounded writable task directory, CPU/memory/PID/disk/wall-clock limits, and no host mounts or Docker socket.
3. No access to host Chrome, host browser profiles, shared browser-harness daemons, shared REPL state, or another task's browser/session.
4. Browser Use API credentials are task-scoped, injected only into the isolated process, never exposed to the app or logged, and revoked on teardown.
5. A task-scoped MCP broker validates SULY user ownership, task/run state, worker lease, runtime identity, and the allowed MCP tool on every call.
6. All outbound traffic passes through a default-deny egress proxy that resolves and blocks loopback, private, link-local, multicast, reserved, metadata-service, and IPv4-mapped IPv6 destinations both before and after redirects/DNS resolution.
7. Domain allowlists are enforced at the proxy/network layer for the entire request chain and subresources, not merely through Browser Use's local-browser settings.
8. Sensitive side effects (submitting forms, sending messages, purchases, account changes, downloads/uploads) require an explicit SULY approval bound to the exact task/run/action. The broker must never trust a model-generated approval.
9. Teardown kills the full process tree, closes the browser, revokes credentials, and removes task state after completion, timeout, cancellation, lease loss, or worker restart.
10. Integration tests prove task A cannot read task B's process environment, files, cookies, browser profile, CDP endpoint, credentials, or network access.

## Current decision

- Keep Browser Use registered as disabled metadata only; do not expose a shared MCP server or host browser.
- Do not treat cloud browser domain rules as an SSRF defense.
- The next implementation unit is an isolated MCP runner plus network egress broker, not a direct client connection to Browser Use.
- No browser automation, cloud browser, provider credential, or live side effect was enabled by this audit.


## URL preflight policy checkpoint — 2026-11-20

- Added `services/api/app/services/browser_network_policy.py` as a fail-closed preflight helper for a future task-scoped browser runtime.
- It requires a task-specific host allowlist, defaults to ports 80/443, rejects userinfo and non-HTTP(S) schemes, blocks IP literals/localhost/.local/.internal names, and rejects any DNS answer that is not globally routable.
- Resolver injection keeps tests deterministic and prevents test suites from making network requests.
- This helper is not wired to Browser Use. It cannot stop DNS rebinding or browser subresource/redirect traffic on its own; the required egress proxy must pin DNS answers at connection time and revalidate every redirect.
