## Context

See proposal.md — Why. The constraint that shapes everything below is that the
runbook can only describe what the repository can actually do, and the repository
is two-environment in its Terraform pipeline and single-environment in three
other places:

- `ansible/playbooks/host-baseline.yml:9` is `hosts: prod` — a literal, not a
  parameter, so no play can target a second environment.
- `ansible/inventory/hcloud.yml` authenticates with one `HCLOUD_TOKEN`, and a
  Hetzner token reaches one project. With a project per environment, the
  inventory sees one environment at a time — and a play matching no host prints
  `skipping: no hosts matched` and **exits 0**.
- `.github/workflows/platform-deploy.yml:54` is `environment: production`, a
  literal, deploying to a single `PLATFORM_DEPLOY_HOST`. The platform stack has
  no per-environment path at all.

The first two are `docs/change-queue.md` entry 50. The third is recorded by this
change, because nothing records it today.

## Goals / Non-Goals

**Goals:**

- A reader following this document ends stage 4 with two servers, both created
  by the pipeline, neither by hand.
- Every decision that is expensive to revisit later is made at the stage where it
  first arises, with the reasoning attached.
- The limits of the second environment are stated where a reader meets them, not
  discovered.

**Non-Goals:**

- Changing any mechanism. No workflow, module, role or Compose file is touched.
- Making the second environment configurable. That is entry 50 and the new entry
  this change records.
- Rewriting stages 5 to 9 for two environments. They gain a statement of what is
  not yet possible; their procedures stay single-host, because that is what the
  system supports.
- Prescribing the second environment's *purpose*. This repository's staging is
  the permanent, application-facing kind; a company may want the ephemeral
  rehearsal kind. The document states the choice and its consequence rather than
  making it.

## Decisions

### 1. Two environments from stage 0, not an appendix

The alternative — keep the single-host procedure and add "Appendix D: adding a
second environment" — is cheaper to write and wrong. The decisions that matter
are made in stages 1 to 3: how many Hetzner projects, which token goes where,
what the read-only secrets are called. An appendix is read after those have been
made for one environment, which is exactly the position this repository was in,
and unwinding it was the expensive part.

The cost is that a reader who genuinely wants one environment now carries a
document about two. That is the right way round: dropping the second environment
is deleting a directory and two secrets, and the document will say so in one
sentence. Adding it later is what this change exists to prevent.

### 2. Both environments are provisioned; only one is configured, and the document says which

Stages 5 to 9 stay single-host. They gain one statement, placed at the top of
stage 5 where the reader arrives with two servers running, naming the three
mechanisms above and the queue entries that close them.

**The wrong shape here would be to write the second host's Ansible and platform
steps as though they worked**, with a note that they do not yet. A runbook whose
steps cannot be followed is worse than one that stops: the reader discovers it
mid-procedure, with a second server already billing.

So the second host ends the document as this repository's staging currently is —
provisioned, reachable by SSH, carrying an attached unmounted volume, and
configured by nothing.

### 3. The company decides one project or two; the document recommends two and says why

`add-a-staging-environment` settled this for *this* repository. A company's
answer could differ, so the document presents it as the decision it is, at stage
1, with the two consequences that are hard to see in advance:

- one project means one Read & Write token, so the lower environment's apply must
  sit behind an approver too — and an approved staging deploy is as slow as prod
  and stops being used;
- Hetzner volume names are unique per project, so one project means the second
  environment's volume takes a different name and therefore a different mount
  path, and `platform/docker-compose.yml`'s hardcoded `/mnt/main-data/...` must
  be parameterised or Prometheus and Grafana come up writing nowhere.

The recommendation is two, and the document says the pipeline supports either.

### 4. Sizing is stated as a pair, prod first

Stage 1.3's sizing table currently has one column of values. It becomes two, with
the lower environment's row explaining the trade this repository made: roughly
half prod's tier, deliberately tight, which is what makes container resource
limits a forcing function rather than a deferral.

### 5. The failure signatures stay with their steps

Three failures cost this repository an afternoon each, and all three are silent
or misleading:

- an HCP **organisation** token in `TF_API_TOKEN` — `terraform init` succeeds and
  the apply dies at `Error acquiring the state lock: resource not found`;
- an Environment omitting `HCLOUD_TOKEN` — GitHub silently resolves the
  repository secret of that name, which at two environments is another
  environment's token;
- a workspace left in HCP's default **Remote** execution mode — the saved-plan
  flow breaks with no message about execution mode.

Each belongs beside the step that can cause it. The first is already there from
`add-a-staging-environment`; the second and third gain their two-environment
form.

### 6. What a reader must not be able to conclude

Two claims the document must not make, and which a careless two-environment
rewrite would make by accident:

- that the second environment can be configured by Ansible today;
- that the platform stack can be deployed to it today.

Both are false, both are load-bearing for a company's planning, and both are
easy to imply merely by describing two environments in a document whose later
stages describe configuring "the host".

### 7. The first push cannot apply anything, and the document must stop implying it can

Stage 4.2 tells the reader to push the template to `main` and read the plan in
the run summary. No plan is produced. `apply.yml`'s changed-path step refuses a
push whose comparison base is unresolvable, and `github.event.before` is all
zeroes on a branch's first push — the workflow's own comment names that case:

> FAILS CLOSED, and this workflow is where that matters most. It runs on `push`,
> where `github.event.before` is all zeroes on a branch's first push and
> unresolvable after a force-push or a history rewrite.

So the very first run of Terraform Apply in a new company repository is red, the
approval never appears, and no server is created. **This is a defect the document
has today at one environment**, inherited rather than introduced — but this
change's first goal is that the reader ends stage 4 with two servers, so it
cannot be left in place.

**The remedy is to give the remote a commit before the content arrives**, so the
content push has a base to compare against. Three details decide whether that is
followable, and each is checkable against this tree:

- **Initialise with a license, not a README.** The template carries a root
  `README.md` and a `.gitignore`; either would collide with the content push as
  an add/add conflict. It carries no root `LICENSE`, so that initialisation is
  conflict-free. A README on the remote, if wanted, is an ordinary edit
  afterwards.
- **Reconcile per history variant.** Stage 3.1 offers two. The keep-history
  variant has history unrelated to the initial commit, so it merges with
  `--allow-unrelated-histories` — one merge commit, no rewrite, and the template
  SHAs stay intact, which is what step 2 says the history is kept for. Rebasing
  it would replay every template commit and defeat that reason. The clean-history
  variant is a single commit and rebases cleanly; that variant also needs step 2's
  `remote set-url` to become `remote add`, and its branch named `main` at `init`.
- **A force-push is not a shortcut**, and it is the first thing an experienced
  operator will reach for. It leaves `github.event.before` pointing at an object
  the checkout cannot resolve, which the *second* guard in the same step refuses
  by name — "a force-push or a rewritten history". The document says so where the
  temptation arises.

**The two reconciliations do not land at the same point in the procedure**, and
the document must place each. The merge can happen at stage 3.1, as soon as the
remote is repointed, because that clone already has commits. The rebase cannot:
the clean-history variant has no commit until the one stage 4.2 creates, and
`git rebase` on an unborn branch fails outright. So it belongs at stage 4.2,
immediately before the push.

The cost is one checkbox at repository creation, a `git fetch`, and one merge or
rebase — plus, for the clean-history variant, a branch-named `init` and a
`remote add` where the document currently says `remote set-url`. No workflow
changes, and the first apply run is a real one that plans both environments.

**A consequence to carry, not to delete.** Stage 3.1 currently ends "Do not push
yet … the first push to `main` triggers the apply workflow, and it must find its
secrets in place." Under this remedy that warning becomes *more* true, not less:
the content push now has a base, so it really does plan, so the secrets really
must exist first. The sentence to correct is any claim that the push at stage 4.2
is the repository's first commit — not the warning itself.

Two alternatives, both rejected. **Two pushes** — let the first be red and treat
the second as the real one — works and needs no reconciliation, but it opens a
company's repository history with a failed production workflow and asks a
first-time operator to distinguish an expected red run from a broken one, on the
day everything is unfamiliar. **A `workflow_dispatch` or a first-push exemption
in `apply.yml`** is forbidden by this change's Non-Goals and would reopen exactly
the hole the fail-closed guard exists to close; if it is wanted, it is a change
of its own.

The document keeps the error text regardless, next to the step, so a reader who
skips the checkbox recognises what they are looking at. That is Decision 5's rule
applied to the failure this change discovered rather than inherited from another.

## Risks / Trade-offs

- **The document grows, and length costs readers** → The two-environment
  material is concentrated in stages 1 to 4, where it is a second column, a
  second row, or a second `gh secret set` line rather than a second narrative.
  Stages 5 to 9 gain one paragraph in total.
- **It describes a state this repository is in and a company may not want** →
  Decision 3 states the project choice as a decision; Decision 1's "dropping the
  second environment" sentence keeps the single-environment path open in one
  edit.
- **The limits it documents will go stale as the queue is delivered** → Each
  limit names its queue entry, so the entry's deletion on archive is the signal
  to revisit the paragraph. That is the same mechanism the rest of `docs/` uses.
- **Two servers is a real recurring cost being recommended by a document** →
  Stated in stage 0, in money and in attention, rather than implied by a
  checklist. A reader who does not want it should stop before stage 1, not after
  stage 4.

## Migration Plan

None: no mechanism changes, and nothing deploys. The document's next reader is
the company setup, and the change is complete when the document describes two
environments and the queue records what is not yet possible.

## Open Questions

None. The three single-environment mechanisms are established by reading the
files, and the scope was settled with the operator before this proposal.
