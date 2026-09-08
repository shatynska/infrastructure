## Context

See `proposal.md` — Why. What follows is only what shapes the configuration.

Three facts were read rather than assumed, and each one settles a decision below.

**Dependabot's Docker Compose file fetcher.** Read from `dependabot-core` on 2026-09-08, at `docker/lib/dependabot/docker_compose/file_fetcher.rb` — note that the `docker_compose` module lives inside the `docker/` directory, so it is not found where the ecosystem's name suggests:

```ruby
FILENAME_REGEX = /(docker-)?compose(-[\w]+)?(?>\.[\w-]+)?\.ya?ml/i

repo_contents(raise_errors: false)
  .select { |f| f.type == "file" && f.name.match?(FILENAME_REGEX) }
  .map    { |f| fetch_file_from_host(f.name) }

# fetch_files: `return fetched_files if fetched_files.any?` else `raise_appropriate_error`
# required_files_message: "Repo must contain a docker-compose.yaml file."
```

Three properties follow. The listing is of the configured directory and selects `type == "file"`, so it **does not recurse**. An empty result **raises** rather than being tolerated. And the pattern is applied with `match?` on the bare filename rather than anchored, so it matches any name containing it.

**The repository's Compose files.** `platform/docker-compose.yml` is the only one this repository owns. `ansible/roles/geerlingguy.docker/tasks/docker-compose.yml` also exists, is an Ansible task list rather than a stack definition, and is Galaxy-installed and gitignored — but it matches `FILENAME_REGEX`, so its exclusion must not rest on the gitignore. Within `platform/`, only `docker-compose.yml` matches; `.env.example` and `README.md` do not.

**PostgreSQL's data is non-durable by policy.** *No Store on This Host Holds Data Requiring Backup* (`openspec/specs/iac-safety-hardening/spec.md`), archived 2026-09-08, classifies `postgres_data` as non-durable — the shared instance admits no durable data at all under *Single Shared PostgreSQL Instance, Per-Application Databases* (`openspec/specs/iac-platform-services/spec.md`). This changes what a bad major-version bump costs, and Decision 3 turns on it.

## Goals / Non-Goals

**Goals:**

- Every image pin in the shared stack produces a pull request when its publisher releases a newer version.
- The configuration's coverage of the tree is asserted statically, so a Compose file added later cannot be silently uncovered.
- The number of gated production deploys a routine week produces stays proportionate to the review each one actually gets.

**Non-Goals:**

- **Detecting a store a bumped image newly declares.** *No Store on This Host Holds Data Requiring Backup* reaches such a store, and nothing here discharges it. Establishing it means reading the upstream image's `VOLUME` declarations, which is a registry call — something `.github/tests` forbids itself and asserts that it forbids. This stays with review of the bump, named in the specification rather than left implied.
- **Deciding whether a proposed tag is a release or a series.** *Shared-Stack Service Images Are Pinned to an Exact Release* already splits that obligation and states why no rule over a tag's shape can close it. Dependabot proposes the publisher's next tag; the floor check and the reviewer decide it, exactly as they do for a hand-written pin.
- **The Molecule platform image digest.** `docs/deferred-work.md` defers it deliberately, its reason is specific to a test-only base image, and this change neither closes nor weakens that entry. The `/platform` scoping means this ecosystem never looks at `ansible/`.
- **Auto-merge of any kind.** Every pull request here reaches production through the `production` Environment's approver.

## Decisions

### Decision 1: `directory: "/platform"`, listed explicitly

The fetcher raises when the configured directory holds no Compose file, and does not recurse. `directory: "/"` therefore does not scan the tree for Compose files — it fails, because the repository root holds none. There is no configuration under which Dependabot discovers Compose files on its own.

*Alternatives considered.* A glob under `directories:` — that key does support `*`, unlike `directory:` — was rejected. It buys nothing here, since one directory holds the only stack, and it makes the set of scanned directories a function of the tree's shape at run time rather than of committed content, which is the opposite of what the assertion in Decision 2 is for. Listing the directory explicitly also matches the `terraform` stanza immediately above it, comment and all, so the file states one policy rather than two.

### Decision 2: assert coverage on **two** conditions — the file's shape decides what must be covered, the fetcher's filename pattern and the configured directories decide whether it is

A file counts as a Compose file for the assertion when it parses as YAML whose top-level `services:` is a mapping and at least one entry declares an `image:`. Such a file is **covered** only when both of the following hold, and is reported as uncovered when either fails:

1. its **name** matches the fetcher's `FILENAME_REGEX`, and
2. its **directory** is one the `docker-compose` ecosystem names.

Both conditions are necessary because the fetcher applies both. Asserting only the directory would pass a stack file named `platform/monitoring.yml` or `platform/stack.yml` — Compose-shaped, sitting in the configured directory, and never fetched, because the name contains no `compose`. That is the precise silent uncoverage this change exists to prevent, reproduced inside the assertion meant to prevent it.

Discovery by shape is what decides the *population*, and it is the point rather than an implementation detail. Dependabot's `FILENAME_REGEX` matches `ansible/roles/geerlingguy.docker/tasks/docker-compose.yml`, which is a task list. Excluding it by path would make this the **third** rule in `.github/tests` deciding which content under `ansible/roles/` is this repository's own — `docs/deferred-work.md` carries an open entry saying there are already two, drawn differently. A shape test adds none: a task list is a YAML sequence with no top-level `services:` mapping, so it drops out on what it is.

Note the asymmetry, because it is what keeps the two conditions from collapsing into one. The filename pattern is used **only to decide coverage of a file shape has already selected**, never to decide whether a file is a stack definition. Decision 2 in an earlier draft rejected "matching Dependabot's own regex and maintaining an exclusion list", and that rejection stands: the objection was to excluding by filename, not to *requiring* the filename of something already known to be a stack.

*Which walker.* The assertion uses the suite's existing `walked_files()` rather than a new `rglob`, because that is the only walk in `.github/tests` that prunes `.claude/worktrees`. `AGENTS.md` requires every change to take a working tree there, and a worktree is a full copy of the tree, so a naive walk finds a phantom `/.claude/worktrees/<name>/platform` and fails from the main working tree. `docs/change-queue.md` entry 34 records that the Dependabot **terraform** assertion already fails this way and owns the general fix; this change declines to add a second assertion with the same defect, and declines equally to add a third pruning rule of its own. Two consequences are accepted and stated rather than discovered later: that walker also prunes `openspec/` and `ansible/roles/geerlingguy.docker`, so a Compose-shaped file under either is outside the assertion's reach — planning artifacts are not deployed, and the Galaxy role would be excluded by shape regardless.

*What it does not establish.* That Dependabot in fact opens a pull request. That is behaviour of a service outside this repository and no test here reaches it. The assertion establishes only that no Compose file the repository holds is one the committed configuration cannot reach.

### Decision 3: no `ignore` stanzas, including for PostgreSQL major versions

A `postgres:16 → 17` bump is the sharpest case, and it is worth stating what it actually costs, because the intuition that it is dangerous is one requirement out of date.

PostgreSQL refuses to start against a `PGDATA` initialised by an earlier major version. It does not attempt an in-place upgrade and does not damage the directory. The container would fail its healthcheck, `docker compose up -d --wait` in the deploy would exit non-zero, and the run would go red. The failure is an **outage** — loud and immediate — not data loss. And under *No Store on This Host Holds Data Requiring Backup* the data in question is non-durable by policy, which makes the remedy (discard the volume, let the instance re-initialise) a legitimate operation rather than a catastrophe.

Against that, an `ignore` is permanent and silent. It suppresses the pull request that would otherwise be this repository's only signal that its PostgreSQL major has reached end of life. That is the failure mode the `terraform` stanza's own comment argues against in the same file: "not partially covered — it is uncovered, and its provider pins rot with no signal at all."

Two human gates already stand in front of the hazard: review of the pull request, and the `production` Environment's approver, who sees the exact diff. A major-version bump is a decision those gates exist to take, not one to remove from them.

*Alternatives considered.* `ignore` on `version-update:semver-major` for `postgres` only — rejected above. `ignore` on major versions across the board — rejected more firmly: Traefik and Grafana majors are exactly the upgrades most worth being told about.

*Consequence accepted.* A PostgreSQL major-bump pull request will appear and will usually be closed rather than merged, until an operator decides to take it together with a volume reset. Closing it is the signal working, not noise.

### Decision 4: one group for the six monitoring images; Traefik and PostgreSQL ungrouped

Eight images on a weekly schedule is up to eight pull requests, each of which — once merged — runs a gated production deploy. Grouping the six monitoring images puts a routine week at three pull requests at most.

**The patterns are written in dependency names, not service names.** Dependabot matches a group's `patterns` against the *dependency* name, which for this ecosystem is the image reference with its tag stripped — not the key the Compose file happens to file the service under. The two differ for **all six** — `grafana` and `grafana/grafana` included — which is exactly why a group written in service names would match nothing at all rather than merely under-matching, leaving Decision 4 inert and every image ungrouped with nothing red to say so:

**Corrected 2026-09-08, after the first Dependabot run contradicted it.** The
two rows carrying a registry host below were originally written *with* that
host, and were wrong: Dependabot builds the dependency as
`Dependency.new(name: details.fetch("image"), ..., source: source_from(details))`
— the image capture group alone, with the registry carried in the source. The
shipped patterns therefore matched nothing, and the assertion covering them was
green because it computed its expected names from this same table. The names
below are now transcribed from pull requests Dependabot actually opened.

| Compose service | Image as written | Dependency name Dependabot matches on |
|---|---|---|
| `prometheus` | `prom/prometheus` | `prom/prometheus` |
| `alertmanager` | `prom/alertmanager` | `prom/alertmanager` |
| `node-exporter` | `prom/node-exporter` | `prom/node-exporter` |
| `postgres-exporter` | `quay.io/prometheuscommunity/postgres-exporter` | `prometheuscommunity/postgres-exporter` |
| `cadvisor` | `ghcr.io/google/cadvisor` | `google/cadvisor` |
| `grafana` | `grafana/grafana` | `grafana/grafana` |
| *(ungrouped)* `postgres` | `postgres` | `postgres` |
| *(ungrouped)* `traefik` | `traefik` | `traefik` |

So the group is `prom/*`, `grafana/*`, `google/cadvisor`,
`prometheuscommunity/postgres-exporter`. **No pattern may match `postgres` or `traefik`** — which is why postgres-exporter is named in full rather than as `postgres*`, a pattern that would silently pull the shared database into a group whose whole purpose is to keep it out. That is Decision 4's own rejected alternative arrived at by a typo, and it is the reason this decision gets an assertion rather than a `grep` in a task.

The split is by blast radius, not by tidiness. Traefik terminates TLS for every public hostname on the host, so a bad Traefik release takes everything offline at once; PostgreSQL is the one grouped-out service holding state. Each deserves its own diff and its own approval decision. The monitoring services fail in a direction that is visible to the operator and not to customers, and they move together in practice.

*Trade-off accepted.* A group is merged or closed whole. One bad member blocks the other five until the group's next run re-proposes without it. For six low-consequence images on a weekly cadence that is cheaper than six separate approvals.

*Alternatives considered.* No grouping — rejected as up to eight gated deploys a week for a single-host stack. One group for all eight — rejected because it puts Traefik and PostgreSQL behind an approval whose diff is dominated by exporter patch bumps, which is how a consequential line gets skimmed.

*What the assertion establishes, and what it does not.* It establishes that the committed patterns select exactly six of the eight images `platform/docker-compose.yml` declares, and neither `postgres` nor `traefik`, under the `*` wildcard semantics Dependabot documents. It does not establish that Dependabot applies those semantics — that is a service outside this repository, the same boundary Decision 2 draws.

**That boundary turned out to be where this decision failed, and the lesson is worth more than the fix.** The assertion computed its expected dependency names with the same helper the configuration had been written from. Both encoded this table, and the table was wrong, so the check established that the configuration and the check agreed — not that either matched Dependabot. A green run of it proved internal consistency and was read as proving correctness. The general form: **a test derived from a belief about an external system cannot verify that belief, and stating the boundary is not the same as guarding it.** The repair is not a better derivation but an anchor — `TestDependencyNamingMatchesWhatDependabotActuallyDid` holds pairs transcribed from pull requests Dependabot actually opened, so the helper is pinned to an observation rather than to a reading. Where an assumption about an external system decides what gets committed, at least one assertion must trace to that system's observed behaviour rather than to our model of it.

### Decision 5: `weekly`, and the default open-pull-request limit

`weekly` matches both existing stanzas. Nothing about images argues for a different cadence, and `daily` would multiply the deploy gate's traffic without shortening the window that matters. `open-pull-requests-limit` is left unset at its default of 5: Decision 4 caps this ecosystem at three concurrent pull requests, so an explicit limit would be a number with no effect, and one fewer value is one fewer thing to keep true.

## Risks / Trade-offs

- **A bumped image declares a persistent store the previous one did not, and it lands unnoticed** → Not closable by anything in this repository's static suite (Non-Goals). Stating it in the specification is necessary and **not sufficient**: a reviewer of a routine bump does not open `openspec/specs/` unprompted. The mitigation that discharges it is the README sentence task 4.2 adds, which names the obligation next to the rest of the dependency story rather than only in the requirement — the same reasoning *Automated Dependency Updates* already applies to a credential's rotation procedure, that a fact whose only home is the change introducing it becomes undocumented at archive. A `.github/pull_request_template.md` was considered and rejected: none exists, and one would put an image-bump question on every pull request this repository opens.
- **A grouped pull request merges six version changes under one approval** → Accepted; the group is deliberately the six lowest-consequence images (Decision 4). The diff still shows every line, and the pinning floor check still runs over all of them.
- **Dependabot proposes a tag that is a series under its publisher's scheme** → Unchanged by this change. The pinning requirement already splits that obligation and already relies on review for the half no check can decide; Dependabot proposes the publisher's own next tag, which is the same input a person would otherwise copy by hand.
- **The coverage assertion is written and then never fails, because a second Compose file is never added** → Accepted. It has the same shape as the `terraform` lockfile-directory assertion, which is also usually green; its value is that the day it would matter is a day nobody is thinking about Dependabot.
- **The fetcher's behaviour was read at a point in time and could change** → The design depends on it in one direction only. Non-recursion makes the configuration *narrower* than a recursive fetcher would be, so if Dependabot later recursed, `/platform` would still cover `platform/docker-compose.yml` and Decision 2's assertion would still hold — the configuration would merely be more conservative than necessary.

## Migration Plan

There is nothing to migrate. The change adds configuration, a specification delta and a test; it converges no host and alters no image pin.

Dependabot begins on its own schedule once the stanza reaches `main` — no enablement step, and no credential. The first run will likely open its full complement of pull requests at once, because eight pins have never been refreshed automatically; that is expected rather than a fault, and Decision 4 caps it at three.

Rollback is deleting the stanza. Any pull request it had opened is closed, and no state on the host is involved.

## Confirmed in production, 2026-09-08

The gate this change had to answer was whether image pins actually produce pull
requests, grouped as Decision 4 specifies. Both halves were observed, and the
first observation is what found the defect.

**First run, after PR #87 merged.** Six pull requests, four of them this
ecosystem's — and four is one more than Decision 4 allows:

| PR | What it was | Verdict |
|---|---|---|
| #89 | the group, with **4** updates | grouped only `prom/*` and `grafana/*` |
| #90 | `traefik` v3.7.10 → v3.7.13 | correctly ungrouped |
| #91 | `postgres` 16.15 → 18.6 | correctly ungrouped |
| #92 | `prometheuscommunity/postgres-exporter` | **escaped the group** |

#92's title and branch path both omitted the registry host, which is what
identified the defect: the two registry-prefixed patterns matched nothing. The
fix is PR #94, and its reasoning is Decision 4's correction above.

**Second run, after PR #94 merged.** Dependabot re-evaluated on its own — no
trigger, no re-run — closed #89 and #92 as superseded, and opened #95: *"Bump
the platform-monitoring-images group across 1 directory with 5 updates"*,
carrying `prom/node-exporter`, `prom/prometheus`, `prom/alertmanager`,
`grafana/grafana` **and `prometheuscommunity/postgres-exporter`**. The
ecosystem's open pull requests then stood at three — #95 grouped, #90 and #91
each alone — which is what Decision 4 specifies.

`google/cadvisor` is still **not** observed. It has opened no pull request
because v0.60.5 remains its latest release, so its corrected pattern is
inferred from the same rule the observed one confirms, and nothing here
establishes it. The anchor test's docstring says so, and the pair should be
added the first time Dependabot names it rather than assumed settled.
