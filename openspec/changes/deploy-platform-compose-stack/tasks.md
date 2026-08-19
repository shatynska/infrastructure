## 1. Compose stack

- [ ] 1.1 Add `platform/docker-compose.yml` with a Traefik service (ACME
      resolver configured, dashboard disabled or access-restricted) and a
      PostgreSQL service (single instance, data volume, credentials sourced
      from `.env`).
- [ ] 1.2 Define an external Docker network in the Compose file, named
      distinctly (e.g. `platform_edge`), that Traefik attaches to and that
      the README documents as the join point for application repos.
- [ ] 1.3 Add `platform/.env.example` documenting every variable the
      Compose file expects, with no real values.
- [ ] 1.4 Update `platform/README.md`'s "Status" section to reflect that
      the stack now exists, and document how an application repo joins the
      shared network.

## 2. GitHub Actions: PR validation

- [ ] 2.1 Extend `.github/workflows/pr-validation.yml`'s existing
      `dorny/paths-filter` step with a new `platform` filter key matching
      `platform/**`. Do NOT add a new workflow file or a workflow-level
      `paths:` trigger — this check is required and must keep reporting on
      every PR, including ones that touch no `platform/**` file.
- [ ] 2.2 Add a step to the same `validate` job, conditioned on
      `steps.changes.outputs.platform == 'true'`, running `docker compose
      -f platform/docker-compose.yml config` with a dummy/example `.env`.
      This step reads no SSH secret and no `environment:` is declared
      anywhere in this job.
- [ ] 2.3 Verify: a PR with intentionally broken Compose YAML fails the
      `validate` check; a PR with valid YAML passes; a PR touching neither
      `terraform/**` nor `platform/**` still reports success (not pending).

## 3. GitHub Actions: gated deploy

- [ ] 3.1 Add a `diff` job to the deploy workflow (`platform-deploy.yml`),
      triggered on the same push-to-`main`-touching-`platform/**` event,
      declaring **no** `environment:` (so it has no access to the deploy
      credential). It SHALL compute the diff this merge introduces under
      `platform/**` using the push event's `before`/`after` SHAs (e.g.
      `git diff ${{ github.event.before }} ${{ github.sha }} --
      platform/`, not an assumption of a single-commit merge) and write it
      to the run's job summary (`$GITHUB_STEP_SUMMARY`).
- [ ] 3.2 Add the deploy job, depending on the `diff` job, triggered the
      same way, declaring `environment: production` (same Environment the
      Terraform apply workflow uses) — so the job summary from 3.1 is
      already visible in the run by the time the approval gate is
      presented.
- [ ] 3.4 Add the deploy SSH private key as a secret scoped to the
      `production` Environment (generated in `bootstrap-ansible-host-
      baseline`'s task 3.2 — do not generate a new keypair here).
- [ ] 3.5 Render `.env` from GitHub Actions secrets in the deploy job (no
      committed file, no plaintext in logs — use `::add-mask::` or secret
      masking as needed).
- [ ] 3.6 `scp` `platform/docker-compose.yml` and the rendered `.env` to
      `/opt/platform/` — the `deploy` account's home directory, already
      provisioned `deploy`-owned by `bootstrap-ansible-host-baseline`. This
      change does not create that directory; if it's missing, fix the
      sibling change rather than adding provisioning logic here.
- [ ] 3.7 `ssh deploy@host chmod 600 /opt/platform/.env` immediately after
      the transfer, so the rendered secrets file isn't left world- or
      group-readable.
- [ ] 3.8 `ssh deploy@host sudo /usr/local/bin/platform-compose-deploy` —
      the one fixed, argument-free command `bootstrap-ansible-host-baseline`
      provisions. Do NOT pass `-f`, a working directory, or any other
      argument — the sudoers rule matches this exact invocation only, and
      the wrapper script already resolves `/opt/platform`'s compose file
      itself.
- [ ] 3.9 No separate post-deploy health-check step is needed:
      `platform-compose-deploy`'s `docker compose up -d --wait` already
      blocks until every service is running/healthy and fails the SSH step
      (and therefore this job) otherwise. Verify this once during initial
      rollout by temporarily breaking a service definition and confirming
      the deploy job fails.
- [ ] 3.10 Add a `concurrency` group (per environment, `cancel-in-progress:
      false`) covering both the `diff` and deploy jobs.
- [ ] 3.11 Verify: merging a `platform/**` change to `main` starts the
      `diff` job immediately (no approval needed), its output appears in
      the run's job summary, and only then does the deploy job pause for
      `production` approval; approving it results in the stack running on
      the host.

## 4. Verification

- [ ] 4.1 Confirm the deploy SSH key is unreadable by the PR validation job
      and by the `diff` job (inspect job permissions/secrets scoping;
      neither declares `environment: production`).
- [ ] 4.2 Confirm two rapid merges to `platform/**` queue rather than race
      (manual test or code inspection of the concurrency group).
- [ ] 4.3 Run `pre-commit run --all-files` (gitleaks in particular) before
      committing `platform/.env.example` to confirm no real secret values
      leaked into it.
