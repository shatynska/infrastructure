## 1. Compose stack

- [x] 1.1 Add `platform/docker-compose.yml` with a Traefik service (ACME
      resolver configured, dashboard disabled or access-restricted) and a
      PostgreSQL service (single instance, data volume, credentials sourced
      from `.env`).
- [x] 1.2 Define an external Docker network in the Compose file, named
      distinctly (e.g. `platform_edge`), that Traefik attaches to and that
      the README documents as the join point for application repos.
- [x] 1.3 Add `platform/.env.example` documenting every variable the
      Compose file expects, with no real values.
- [x] 1.4 Update `platform/README.md`'s "Status" section to reflect that
      the stack now exists, and document how an application repo joins the
      shared network.

## 2. GitHub Actions: PR validation

- [x] 2.1 Extend `.github/workflows/pr-validation.yml`'s existing
      `dorny/paths-filter` step with a new `platform` filter key matching
      `platform/**`. Do NOT add a new workflow file or a workflow-level
      `paths:` trigger — this check is required and must keep reporting on
      every PR, including ones that touch no `platform/**` file.
- [x] 2.2 Add a step to the same `validate` job, conditioned on
      `steps.changes.outputs.platform == 'true'`, running `docker compose
      -f platform/docker-compose.yml config` with a dummy/example `.env`.
      This step reads no SSH secret and no `environment:` is declared
      anywhere in this job.
- [x] 2.3 Verified against real GitHub PRs, all three sub-cases: a PR
      with intentionally broken Compose YAML (a throwaway PR, closed
      without merging) failed `validate` at exactly the `docker compose
      config` step (`yaml: line 53: did not find expected node content`);
      PRs #31/#32/#34 with valid `platform/**` changes all passed; PR #33
      (touching neither `terraform/**` nor `platform/**`) still reported
      success rather than pending.

## 3. GitHub Actions: gated deploy

- [x] 3.1 Add a `diff` job to the deploy workflow (`platform-deploy.yml`),
      triggered on the same push-to-`main`-touching-`platform/**` event,
      declaring **no** `environment:` (so it has no access to the deploy
      credential). It SHALL compute the diff this merge introduces under
      `platform/**` using the push event's `before`/`after` SHAs (e.g.
      `git diff ${{ github.event.before }} ${{ github.sha }} --
      platform/`, not an assumption of a single-commit merge) and write it
      to the run's job summary (`$GITHUB_STEP_SUMMARY`).
- [x] 3.2 Add the deploy job, depending on the `diff` job, triggered the
      same way, declaring `environment: production` (same Environment the
      Terraform apply workflow uses) — so the job summary from 3.1 is
      already visible in the run by the time the approval gate is
      presented.
- [x] 3.4 **Operator action, done.** `PLATFORM_DEPLOY_SSH_KEY`,
      `PLATFORM_DEPLOY_HOST`, `PLATFORM_ACME_EMAIL`,
      `PLATFORM_POSTGRES_USER`, and `PLATFORM_POSTGRES_PASSWORD` all added
      to the `production` Environment; confirmed working end-to-end by a
      real successful deploy run.
- [x] 3.5 Render `.env` from GitHub Actions secrets in the deploy job (no
      committed file, no plaintext in logs — use `::add-mask::` or secret
      masking as needed).
- [x] 3.6 `scp` `platform/docker-compose.yml` and the rendered `.env` to
      `/opt/platform/` — the `deploy` account's home directory, already
      provisioned `deploy`-owned by `bootstrap-ansible-host-baseline`. This
      change does not create that directory; if it's missing, fix the
      sibling change rather than adding provisioning logic here.
- [x] 3.7 `ssh deploy@host chmod 600 /opt/platform/.env` immediately after
      the transfer, so the rendered secrets file isn't left world- or
      group-readable.
- [x] 3.8 `ssh deploy@host sudo /usr/local/bin/platform-compose-deploy` —
      the one fixed, argument-free command `bootstrap-ansible-host-baseline`
      provisions. Do NOT pass `-f`, a working directory, or any other
      argument — the sudoers rule matches this exact invocation only, and
      the wrapper script already resolves `/opt/platform`'s compose file
      itself.
- [x] 3.9 Verified against a real deploy run: `platform-compose-deploy`'s
      `docker compose up -d --wait` reported both `platform-traefik-1` and
      `platform-postgres-1` as `Healthy` before the job completed — no
      separate health-check step was needed.
- [x] 3.10 Add a `concurrency` group (per environment, `cancel-in-progress:
      false`) covering both the `diff` and deploy jobs. Declared once at
      the workflow level (`group: platform-deploy`), which covers every
      job in the run — GitHub Actions concurrency groups apply per
      workflow run, not per job.
- [x] 3.11 Verified against a real merge to `main` (run 32350184847):
      the `diff` job started immediately with no approval needed and
      posted the `platform/` diff to the job summary; the `deploy` job
      then paused for `production` approval; approving it resulted in the
      stack (Traefik + Postgres) actually running on the host.

## 4. Verification

- [x] 4.1 Confirm the deploy SSH key is unreadable by the PR validation job
      and by the `diff` job (inspect job permissions/secrets scoping;
      neither declares `environment: production`). Confirmed by code
      inspection: `pr-validation.yml`'s `validate` job and
      `platform-deploy.yml`'s `diff` job both declare no `environment:`,
      and `secrets.PLATFORM_DEPLOY_SSH_KEY` appears nowhere in either.
- [x] 4.2 Confirm two rapid merges to `platform/**` queue rather than race
      (manual test or code inspection of the concurrency group). Confirmed
      by code inspection: `platform-deploy.yml` declares one workflow-level
      `concurrency.group: platform-deploy` with `cancel-in-progress:
      false`, covering the whole run (both jobs), not parameterized by
      branch/PR — every run of this workflow queues behind the previous
      one. A live two-merges-in-quick-succession test still needs a real
      GitHub run to fully confirm.
- [x] 4.3 Run `pre-commit run --all-files` (gitleaks in particular) before
      committing `platform/.env.example` to confirm no real secret values
      leaked into it. Ran in this pass: gitleaks ("Detect hardcoded
      secrets") passes clean across all new/changed files. `tflint`
      failed in the same run, but only because the `tflint` binary isn't
      installed in this sandbox — unrelated to this change, which touches
      no Terraform files.
