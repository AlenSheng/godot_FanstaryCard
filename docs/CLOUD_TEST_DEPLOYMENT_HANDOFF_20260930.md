# WIP cloud environment and controlled test deployment handoff

Status: **unfinished; not approved for deployment**. Local editing stops after this
checkpoint is pushed. Continue in the newly published Codex Cloud environment.
No server deployment, credential creation, secret entry, permission change,
runner registration, merge or auto-merge was performed.

## Repository and isolation

- Canonical repository: `AlenSheng/godot_FanstaryCard` (private).
- GitHub connector verified default branch: `main`, 2026-09-30.
- Checkpoint branch: `codex/cloud-test-deployment-20260930`.
- Base: `release@28c6c7e7d3898e4d2abd186f53361477ba380330`.
- Isolated local checkout: `C:\Users\79498\Documents\Codex\2026-09-30\task-2\repo`.
- The existing PR13 working tree at `F:\GitHubFiles\godot_FanstaryCard` was read
  only. Its branch, edits and commits were not changed. No test server mutations.
- Local clone uses an object alternates reference to the historical checkout.
  Cloud continuation must clone from GitHub; it must not use this local path.
- `server/AGENTS.md` references `.agents/skills/server_create/SKILL.md`, which was
  absent in the repository and searched skill locations. This checkpoint changes
  no `server/` files. Recover that skill before future server implementation work.

## Existing implementation reused

Six workflows exist: `gameplay-load.yml`, `numerical-regression.yml`,
`numerical-client.yml`, `numerical-acceptance.yml`, `numerical-source-audit.yml`
and `pr13-plan.yml`. They already cover Domain/server regressions, Godot fixtures,
disposable PostgreSQL, numerical checks and evidence. The checkpoint invokes the
existing server tests and Dockerfile. It extracts the existing updater's TLS,
readiness and admin exposure health checks without executing its update logic.

`server/deploy/fantasycard-update.sh` follows a branch and uses
`/tmp/fantasycard-update.lock`, database backups and health checks. It does not
automatically roll back. The proposed controller shares that same lock and uses
the existing `server/compose.cloud.yaml` and server `.env`; it only replaces the
application image via a separate Compose override.

## Proposed files and current behavior

| File | Purpose |
| --- | --- |
| `.github/workflows/test-server-deploy.yml` | Manual dispatch, trusted main controller, full same-repository PR SHA, separate tests/build and protected deployment jobs, immutable image artifact and sanitized evidence. |
| `tools/cloud/toolchain.json` | Official .NET 10.0.400 and Godot 4.7.2 URLs and reviewed hashes; PG major 18. |
| `tools/cloud/install_tools.py` | Verify downloaded tool bytes before extraction, Linux x64 only. |
| `tools/cloud/setup.sh` | Install dependencies in a disposable Ubuntu cloud environment and cache NuGet. |
| `tools/cloud/env.sh` | Explicit per-shell tool paths and local test database connection. |
| `tools/cloud/start.sh` | Start disposable PG18 on loopback port 55432 and refresh restore. |
| `tools/cloud/check.sh` | Intended environment smoke/regression command; currently incomplete. |
| `tools/cloud/deployment.py` | Input, PR, default branch and environment protection validation; provenance manifest and existing health extraction. |
| `tools/cloud/remote_deploy.py` | Fixed-path server preflight, schema/config gate, backup, immutable image activation, health check and rollback state machine. |
| `tools/cloud/ship.py` | Strict SSH, fixed host/user/port, trusted controller transport, checksum validation and sanitized evidence retrieval. |
| `tools/cloud/.gitignore` | Exclude local tool and Python caches. |

The controller refuses a moving PR head, forks, a controller ref other than
`main`, a changed default branch, a disabled gate, an unapproved controller SHA,
missing reviewers, admin bypass, or environment branch policy other than main.
These gates are implemented but their remote operation is **not tested**.

The build job has no server secrets. The deployment job checks out only the
trusted controller, downloads the exact current-run artifact ID, regenerates the
health script from that trusted checkout and transfers a full image ID. No
user-entered value is directly inserted into shell code. SSH targets are fixed
to `ubuntu@43.172.70.182:22` and require a verified host-key entry.

## Verified and unverified evidence

| Evidence | Current status |
| --- | --- |
| Repository identity / actual default branch | Verified with connected GitHub metadata. |
| Official .NET SDK 10.0.400 Linux x64 hash | Verified against Microsoft's release metadata. |
| Official Godot 4.7.2 Linux x64 digest | Verified against official godot-builds release asset metadata. |
| Actions checkout/setup-dotnet/upload/download commit pins | Verified against official action repository tag metadata. |
| Python compilation of four new modules | Passed locally. |
| Bash syntax of setup/start/env/check | Passed locally, each script individually. |
| Workflow YAML parsing | Passed locally with workspace-local PyYAML 6.0.3. |
| Functional unit tests / actionlint / cloud install | Not executed in this checkpoint. |
| Domain/server tests, Docker build, live rollout/rollback | Not executed in this checkpoint. |
| GitHub Environment protection settings / plan capability | Cannot be read with the exposed connector actions; must be verified by owner or cloud Actions preflight. No secrets were read. |
| Parent task's published cloud environment | Parent reports published, new task is verifying dependencies; this local task did not independently verify it. |
| Parent task's temporary PostgreSQL18.6 integration check | Parent reports 21/21 passed. It does not validate this new setup script. |

No test failure was hidden: no functional test suite was started. Initial public
metadata downloads were blocked by the sandbox network and succeeded using
authorized read-only escalation. An unauthenticated request for this private
repository returned 404; repository identity came from the authorized connector.
Actionlint metadata was obtained but its binary was not downloaded or run.

## Confirmed old test-server baseline

The parent task's read-only checks established:

- Checkout, deployed-git-commit, deployed-runtime-commit and image revision:
  `8489fe97c7da71e1a5bfe1a860faf86fd4e0a4af`.
- Immutable image ID:
  `sha256:e7defa05caeb1188afb4cfc4390d96900bfc10afb4996ced23a042fb09132697`.
- Existing service configuration: `/opt/fantasycard-github/server/compose.cloud.yaml`.
- Backup/state location: `/opt/fantasycard-app`.

This is an old version, not current PR13. Re-read the baseline under the shared
lock before deployment. The proposed controller leaves checkout and the old
deployed-git marker unchanged, writes deployed-runtime only after acceptance,
and records both checkout and runtime source separately. Do not run the legacy
branch updater while the controlled image override is active.

## Secrets and owner actions

Only the owner should enter these through GitHub's secure Environment UI:

| Environment secret | Purpose and boundary |
| --- | --- |
| `TEST_SERVER_SSH_KEY` | Private key for the existing ubuntu test-server account. Its existing sudo Docker access can control the server; do not describe it as a narrowly scoped account. Available only to the approved deployment job. Never put it in Cloud, source, an artifact, or a normal PR job. |
| `TEST_SERVER_KNOWN_HOSTS` | Trusted public SSH host-key record beginning `43.172.70.182`. Verify via a trusted channel, not an unverified scan. It is public integrity data, stored alongside the private key for controlled entry. |

Environment name: `silicon-valley-test`. Require an owner-designated reviewer,
restrict its branch policy to main, and disable administrator bypass. Actual
feature availability for this private repository is still unknown. GitHub's
documentation makes availability plan-dependent. If unavailable, remain blocked
and obtain an explicitly approved alternative; do not silently remove the gate.

Repository variables (not secret values): leave `TEST_DEPLOY_ENABLED` unset or
false until setup is verified; then set `TEST_DEPLOY_APPROVED_WORKFLOW_SHA` to the
full reviewed controller commit on main. This checkpoint does not enable them.

The automatic GitHub token needs only contents/actions/pull-requests read in
preflight/deployment; no PAT, GHCR password, DB password or admin API key is needed.
Server secrets remain in the existing `.env`. Creating a new key/account,
changing permissions/firewall, installing a runner, or adding persistent access
requires separate explicit approval. This checkpoint performs none of them.

## Continuation checklist

| Owner | Dependency / action | Completion criterion |
| --- | --- | --- |
| Cloud development task | Read this checkpoint and inspect full diff before continuing. | Verify exact remote commit SHA; preserve PR13 concurrency boundary. |
| Cloud development task | Add `tools/cloud/tests` and `.github/workflows/cloud-config-check.yml`. | Meaningful tests cover invalid/moving/fork PRs, manifest tampering, partial activation, failed readiness, rollback success/failure, signals and marker failures. |
| Cloud development task | Run actionlint, Bash/Python checks, and isolated installation tests. | Evidence for correct install, idempotent restart, cached NuGet and PG18; correct the current `check.sh` reference to the not-yet-created cloud tests. |
| Cloud development task | Review and test remote controller using fake commands, then disposable Docker stack. | Prove immutable source/image selection, backups, rollback and safe evidence without secrets. |
| Cloud development task | Fix/decide the external readiness boundary in `ship.py`. | Currently external readiness is checked after remote acceptance; an external failure does not roll back. Do not call that a complete deployment acceptance. |
| Cloud development task | Test interrupted rollout and post-acceptance state writes. | SIGKILL/machine-loss still requires manual recovery; verify marker/evidence consistency and avoid accepted state on failed persistence. |
| Owner / parent | Verify environment settings and private-repo reviewer capability. | Capture settings names/protection state, never secret values; preflight succeeds safely. |
| Owner | Securely enter the two Environment Secrets. | Strict SSH host identity and current account access verified without logging the private key. |
| Owner / reviewer | Review and separately authorize merging controller into main. | This WIP is not merged; manual dispatch cannot work until workflow exists on default branch. |
| PR13 agent / parent | Freeze target SHA and coordinate server exclusivity. | Latest accepted test/build SHA is explicit; no simultaneous server modifications. |
| Parent / cloud task | Configure published environment's Install script / Start skill with reviewed commands. | New cloud task starts dependencies successfully with personal computer offline. Do not use a local Windows path. |
| Authorized cloud task | Run controlled deployment only after all gates above pass. | Match source SHA, artifact checksum and image ID; readiness/TLS/admin checks and rollback drill pass; logs/artifacts returned. |

Cloud Install script candidate: `bash tools/cloud/setup.sh`; Start skill candidate:
source `tools/cloud/env.sh`, run `bash tools/cloud/start.sh`, then verify versions
and PG readiness. These scripts only exist on this checkpoint branch; arrange a
reviewed branch or immutable script bundle before starting a task at PR13's branch.
Do not confuse the current Cloud UI's Install script / Start skill with legacy
setup/maintenance fields.

Neither a green CI nor this deployment smoke test accepts all PR13 items. Its
132-item/396-case acceptance register remains independent and incomplete.

## Official references

- [Current Codex Cloud environments](https://learn.chatgpt.com/docs/environments/cloud-environments)
- [.NET release metadata](https://builds.dotnet.microsoft.com/dotnet/release-metadata/10.0/releases.json)
- [Godot official release](https://github.com/godotengine/godot-builds/releases/tag/4.7.2-stable)
- [GitHub environment capabilities](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)

The exact checkpoint commit and draft PR URL are supplied with the handoff response.
