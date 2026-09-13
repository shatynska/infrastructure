# Handoff — `rename-the-github-environments`

`docs/change-queue.md` entry 75. Opened 2026-09-13 by the session that recorded the Alertmanager check's timing divergence. There is no proposal yet: writing it is the first job of the session that takes this up.

**Read entry 75 in `docs/change-queue.md` first.** It carries the reasoning, the measured facts about GitHub's Environment API and the two failure modes. This file carries the live state, measured rather than assumed, and the things a queue entry has no room for.

## Live state, measured 2026-09-13

    gh api repos/shatynska/infrastructure/environments

| Environment | Created | Secrets | Protection rules |
|---|---|---|---|
| `main-production` | 2026-09-12T06:11:52Z | 0 | required reviewer (`shatynska`) |
| `production` | 2026-07-26T06:02:23Z | 15 | required reviewer (`shatynska`) |
| `staging` | 2026-09-10T08:14:33Z | 6 | none — ungated by design |
| `main-staging` | — | — | does not exist |

`main-production` already exists. It was created by hand on 2026-09-12 as `rename-the-external-services`'s cheapest probe of whether an Environment can be renamed; the probe returned no, and it was left in place for this change, which needs the name. **It has since been given the required reviewer** — an earlier draft of this handoff recorded it as having no protection rules, which was true when that draft was written and is not true now. Re-measure before relying on either sentence.

**Protect before pointing, and verify the protection took.** A job naming an Environment attaches to whatever is there, and GitHub does not fail on an Environment carrying no rules — it just runs. So the required reviewer belongs on each new Environment *before* any `github_environment` value moves, and the check is `gh api repos/<owner>/infrastructure/environments`, because nothing in this repository can see it: `.github/tests` may not make a network call, and that prohibition is itself asserted there.

## The 21 secrets

**production (15):** `ANSIBLE_SSH_PRIVATE_KEY`, `ANSIBLE_VAULT_PASSWORD`, `HCLOUD_TOKEN`, `PLATFORM_ACME_EMAIL`, `PLATFORM_DEADMANSWITCH_URL`, `PLATFORM_DEPLOY_HOST`, `PLATFORM_DEPLOY_SSH_KEY`, `PLATFORM_GRAFANA_ADMIN_PASSWORD`, `PLATFORM_POSTGRES_EXPORTER_PASSWORD`, `PLATFORM_POSTGRES_PASSWORD`, `PLATFORM_POSTGRES_USER`, `PLATFORM_SLACK_WEBHOOK_URL`, `TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_SECRET`, `TF_API_TOKEN`.

**staging (6):** `ANSIBLE_SSH_PRIVATE_KEY`, `ANSIBLE_VAULT_PASSWORD`, `HCLOUD_TOKEN`, `TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_SECRET`, `TF_API_TOKEN`.

**Stop and establish, before touching anything, that the password manager actually holds the eighteen recoverable values.** A secret's value cannot be read back out of GitHub. If any of the eighteen is missing, the scope grows from *re-enter* to *regenerate*, and that is a decision to take at the start rather than halfway through.

**Three are not recoverable**, because `docs/bootstrap-a-new-host.md` §0.3 has the operator delete the local private half once it is stored:

- **`ANSIBLE_SSH_PRIVATE_KEY`, twice** — one converge key per stack. Rotating means generating a keypair and appending the public half to `/root/.ssh/authorized_keys` on that host by hand, over the tailnet; no role owns that file, which §0.3 already calls a gap. Verify the new key actually logs in before deleting the old Environment, per §6.6's check line — a key installed but not usable fails the pipeline rather than the person who installed it.
- **`PLATFORM_DEPLOY_SSH_KEY`** — production's platform deploy key. Its public half lives in `ansible/inventory/group_vars/production.yml` under `deploy_apps`, so rotating it is a commit **and** a production converge before the new key works. Sequence that deliberately.

## The asymmetry that decides the ordering

Measured 2026-09-12 and worth not rediscovering: `gh secret set --env <name>` **fails loudly** on an unknown Environment, with a `404` from the public-key fetch; a workflow's own `environment:` key does the opposite, and **creates** the Environment it names, with no protection rules. So secrets-first is safe and pointing-jobs-first is not. Create, populate, protect, verify — and only then move any `github_environment` value.

## What must move together

Each stack's own declaration is what the pipeline reads; no workflow names a stack or an Environment, with one exception:

- `terraform/stacks/main-production/pipeline.yml:33` — `github_environment: production`
- `terraform/stacks/main-staging/pipeline.yml:25` — `github_environment: staging`
- `.github/workflows/platform-deploy.yml:65` — a **literal** `environment: production`, which `.github/tests` asserts equals the production stack's declared value, because *Gated Deploy Reuses the Terraform Production Environment* (`openspec/specs/iac-platform-deploy-pipeline/spec.md`) obliges the same Environment to gate both.

**`target_environment` stays on the environment axis in both files**, and this change must not touch it: it names the Ansible group, the `--vault-id` label and the `group_vars` file. The same holds for `--env` in §6.6's `gh secret set` lines and for the Ansible groups `production` and `staging`.

## The commitments this change owns

Comments and sentences that point at entry 75 are a commitment to do this work, and deleting them is part of it. As of 2026-09-13:

    terraform/stacks/main-production/pipeline.yml:32, :90
    terraform/stacks/main-staging/pipeline.yml:24
    .github/workflows/platform-deploy.yml:63
    .github/tests/test_the_external_service_names_are_retired.py:471, :475
    .github/tests/test_environment_agnostic_pipeline.py:978, :985
    .github/tests/test_a_second_environment.py:143
    docs/bootstrap-a-new-host.md:115, :246, :269, :747, :959
    docs/naming-conventions.md:5 (the banner), :51
    README.md:131

Re-run this to catch any that moved, and note that this handoff is itself a hit until the change is archived:

    grep -rn "entry 75" --include=*.yml --include=*.py --include=*.md --include=*.tf . | grep -v openspec/changes/archive

`docs/naming-conventions.md`'s banner says whoever archives 75 deletes it. That is this change, and the tree then matches the scheme with no exception.

## What it must not undo

- Entry 63's work: the HCP workspaces, the two read-only repository secrets and the Hetzner projects already carry the stack names.
- The `production` Environment's required reviewer. It must exist on the **new** Environment before the old one is deleted, not after.
- §6.6's note that `--env` takes the environment. After this change it takes the stack, and that paragraph says so explicitly — update it rather than deleting it.

## The verification this change owes

The usual three — the `.github/tests` suite, `openspec validate --all`, pre-commit — prove nothing whatever about GitHub, for the reason given above. The real verification is operator observation:

- a production apply, converge and platform deploy each **wait** for approval under the new Environment;
- staging's apply still does **not**;
- `gh api repos/<owner>/infrastructure/environments` shows the two new names, the old two gone, and the reviewer on the production one.

Do the first of those on a real merge rather than a dispatch, and read which **workflow** the prompt names: all three gate on one Environment and render identical text, which is `docs/change-queue.md` entry 77.
