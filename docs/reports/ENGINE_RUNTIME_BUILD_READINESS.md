# SULY — Engine Source and Runtime Build Readiness

**Checkpoint date:** 2026-11-21  
**Branch:** `main`  
**Status:** Source pins and backend runtime code present; image-build pipeline added; external deployment deliberately not performed.

## 1. Immutable upstream source inclusion

SULY tracks both complete upstream repositories as independent Git submodules. A recursive checkout materializes their complete source trees under the SULY repository:

| Engine | Upstream | Pinned revision | License |
|---|---|---|---|
| Hermes Agent | `NousResearch/hermes-agent` | `2de9f51b8008a7d49a49221c184f2f11cbfc4af1` | MIT |
| OpenCode | `anomalyco/opencode` | `4cca18d80450a3dd6a9a4142028bde84ccb3116e` | MIT |

The Git tree records immutable submodule gitlinks. The full upstream file contents are materialized by a recursive clone/checkout; a GitHub tree view of the parent repository displays the gitlink rather than expanding every upstream file. The original upstream licenses and source histories are retained in their submodules.

The required checkout is:

```sh
git clone --recurse-submodules https://github.com/eslammohamedk123450-netizen/Open-suly.git
# For an existing clone:
git submodule update --init --recursive
```

## 2. Independent original engine images

- OpenCode uses `engines/opencode/Dockerfile`, copies the complete pinned upstream monorepo into its own image, and installs from the upstream frozen Bun lockfile.
- Hermes uses its own upstream `Dockerfile` directly from `engines/hermes/upstream`; it is not copied into the SULY FastAPI environment.
- The runtime provisioner has its own image from `services/runtime-provisioner/Dockerfile`.

The new workflow `.github/workflows/engine-runtime-build.yml` performs a recursive source checkout, checks both exact source pins and license/build files, verifies OpenCode provenance, then builds both original engine images and the provisioner image. It records local image IDs in the CI job.

The workflow intentionally does not push images to a registry, publish credentials, deploy a worker host, or change live SULY configuration. Those are external deployment steps and remain separate from source/build completion.

## 3. Backend runtime wiring already present

The backend provisioner supports two distinct engine identities and images:

- `OPENCODE_RUNTIME_IMAGE` for OpenCode.
- `HERMES_RUNTIME_IMAGE` for Hermes.

Both image values must be immutable digest references (`@sha256:...`). The provisioner selects a dedicated manager per engine and creates a fresh task-attempt container, internal Docker network, workspace, credentials, and expiry/teardown record. Hermes additionally requires `suly-hermes-task-v1`, starts its native API on port 8642, and is checked through its authenticated capabilities endpoint. OpenCode starts its native server on port 4096 and is checked through its authenticated info endpoint.

The API worker has separate `opencode.task.run` and `hermes.agent.turn` handlers. Runtime identity is bound to SULY task/engine-run ownership and recovered/released through the provisioner. Cross-engine collaboration is mediated by SULY contracts; the engines do not share a process, writable workspace, runtime credential, or live session.

## 4. What this checkpoint establishes

- Both original upstream repositories are pinned as independent complete-source submodules.
- The repository has reproducible CI build instructions for both original engine images.
- The runtime provisioner image has a build definition and is included in the new build workflow.
- The backend contains distinct per-engine runtime managers and task-worker adapters.
- The new workflow is committed on `main`.

## 5. What this checkpoint does not claim

- No local or production Docker image was built by this GitHub connector action.
- No image was pushed to a registry and no immutable registry digest has been produced.
- No external provisioner host, TLS gateway, firewall, or model-provider egress gateway was deployed.
- No live model inference or user task was executed.
- No Supabase migrations were applied.
- No end-to-end or security tests were run as part of this checkpoint.

## 6. Remaining external activation steps after code/build readiness

1. Run the new image-build workflow and retain the two engine image digests.
2. Publish those images to the selected private registry.
3. Deploy the runtime provisioner on a dedicated Docker worker host with TLS ingress and the required server-only secrets.
4. Configure the API worker with the provisioner URL/token/origin allowlist and both digest-pinned image references.
5. Configure a task-aware model-provider egress gateway; direct task-container egress remains denied by design.
6. Reconcile and apply the pending ordered Supabase migrations in staging, verify RLS/RPC behavior, then deploy the API and worker.
7. Run real container isolation, cancellation, recovery, teardown, and cross-tenant tests before enabling either engine for users.

Keep `worker_enabled`, `opencode_enabled`, `hermes_agent_enabled`, and the Hermes isolation attestation disabled until those deployment and verification gates pass.
