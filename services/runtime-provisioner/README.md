# Isolated OpenCode Docker runtime (provisioner component)

This component is a Docker lifecycle primitive, not yet a deployable public provisioner API. It is intentionally separate from the SULY FastAPI application: the public API must never receive Docker socket access.

## Implemented in this checkpoint

- One fresh Docker bridge network and container per task attempt.
- A unique, mode-0700 host workspace populated from a bounded file snapshot.
- Strict relative-path validation, traversal rejection, reserved secret-directory rejection, 200-file and byte limits.
- Digest-pinned image requirement.
- Read-only container root, non-root image user, all Linux capabilities dropped, no-new-privileges, no privileged mode, PID/CPU/RAM/swap/tmpfs limits.
- OpenCode port publication is bound to loopback only. A non-loopback binding is rejected and partially-created resources are torn down.
- Exact task/run/runtime Docker labels are checked before destroy.
- Expiry metadata and a label-scoped orphan cleanup routine.

## Required deployment controls (do not skip)

1. Run this service on a dedicated worker host/VM with a dedicated Docker daemon. Do not mount the Docker socket into the public API, web app, or an untrusted container. Docker socket access is effectively host-root access.
2. The service must authenticate SULY with a high-entropy bearer secret and use TLS at its ingress. The HTTP provisioner API and gateway routing layer are not included in this checkpoint.
3. The per-runtime bridge network is unique, so task containers are not attached to one another's networks. However, bridge networking still permits outbound traffic. Enforce host-level egress firewall rules before production; allow only approved SULY AI gateway/provider endpoints and required DNS. Block cloud metadata, host management ports, private control-plane ranges, and Docker daemon endpoints. Docker bridge isolation is not an egress firewall.
4. A TLS runtime gateway must map each opaque runtime ID to its loopback-only host port, enforce the per-runtime token, reject unknown hosts, and remove routes on release/expiry. Never expose the published loopback port publicly.
5. Mount only the task workspace. Never mount the Docker socket, host root, home directories, Supabase credentials, or other users' files into a runtime.
6. Store runtime IDs, task/run ownership, expiry, port mapping, and credential hashes in a durable control-plane store. Return the bearer token once only; never log it. Rotate/revoke it on release.
7. Configure an external watchdog to call cleanup after crashes/restarts. In-process cleanup is not a substitute for durable lease reconciliation.

## Build

Build and push the OpenCode image from the SULY repository root, then configure DockerTaskRuntimeManager with its immutable repository@sha256:<digest> image reference. Never use a floating latest tag.

## Verification

Run from services/runtime-provisioner: install requirements, install pytest, then run pytest -q tests.

The tests use a fake Docker client. They verify configuration and ownership guards; they do not claim a real Docker daemon, TLS gateway, egress firewall, or end-to-end OpenCode execution has been tested.
