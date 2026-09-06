## Context

See `proposal.md` — Why. Two constraints shape the approach and neither is
obvious from the files alone:

- **`geerlingguy/docker-ubuntu2204-ansible` publishes exactly one tag.** The
  Docker Hub tag listing for that repository returns `count: 1` — `latest`,
  and nothing else. There is no `2204-1.2.3` or dated tag to move to. Whatever
  pin this change adopts, it is a digest, because no version tag exists.
- **The image is multi-architecture.** `latest` is a manifest list over
  `linux/amd64` (`sha256:ede3998c…`) and `linux/arm64`
  (`sha256:ca81a4cd…`). CI runs on `ubuntu-latest` (amd64); a developer
  machine may be either.
- **`ansible/roles/` is not exclusively this repository's.**
  `ansible/requirements.yml` pins `geerlingguy.docker`, and
  `ansible-verify.yml:113-117` installs it with `-p ansible/roles` — it has to,
  because each scenario overrides `ANSIBLE_ROLES_PATH` to that directory and a
  role installed to the default `~/.ansible/roles` is never found. It is
  gitignored (`.gitignore:30`), and it ships a scenario of its own at
  `ansible/roles/geerlingguy.docker/molecule/default/molecule.yml`, whose image
  is `geerlingguy/docker-${MOLECULE_DISTRO:-rockylinux9}-ansible:latest`.
  So the obvious glob for "every scenario" yields nine files on a provisioned
  machine and eight on a runner that has not installed Galaxy content yet.
  (`ansible-verify.yml`'s own role discovery is unaffected today only because
  it runs in a separate job that checks out and discovers before any install.)

The `platform_data_volume` failure was also re-diagnosed as part of writing
this plan, and the cause recorded in `docs/change-queue.md` entry 8 is wrong in
one detail that changes nothing about the fix but matters for anyone reading
the entry: uid `65534` **does** resolve inside the image, to `nobody`. Verified
directly against the pinned digest — `getent passwd 65534` returns
`nobody:x:65534:65534:…`, `getent passwd 472` returns nothing, and likewise for
the groups. The scenario declares two subdirectory fixtures; it is the
`grafana` one (`472/472`) that has no `passwd`/`group` record and therefore no
`pw_name` key on its `stat` result.

## Goals / Non-Goals

**Goals:**

- Every Molecule scenario resolves the same immutable image reference on every
  machine and every run — with each architecture resolving deterministically
  beneath it — and a re-push upstream cannot change what it resolves to
  silently.
- The `platform_data_volume` scenario passes for the right reason — because the
  subdirectories genuinely have the declared ownership, not because an
  assertion was softened.
- The pinning obligation survives the next scenario someone adds, without
  depending on a reviewer noticing.

**Non-Goals:**

- Refreshing the digest automatically. Nothing in this change updates it, and
  nothing is added that would — see Risks.
- Promoting `ansible-verify.yml` to a required status check, or touching its
  `paths:` filter. That is `docs/change-queue.md` entry 4 and needs evidence
  this change does not yet produce.
- Any change to `platform_data_volume`'s role code. The defect is in the
  scenario that verifies the role, not in the role.

## Decisions

### 1. Pin as `repo:tag@sha256:…`, not `repo@sha256:…`

The digest is what Docker resolves; the tag alongside it is for the human
reading the file, who would otherwise see a bare 64-hex string with no
indication of what image it is. Docker accepts the combined form and ignores
the tag when a digest is present.

Verified rather than assumed: `docker pull
geerlingguy/docker-ubuntu2204-ansible:latest@sha256:0172e3b5…` succeeds and
reports `Downloaded newer image for
geerlingguy/docker-ubuntu2204-ansible@sha256:0172e3b5…`.

**What that did not establish, and implementation disproved.** This decision
originally went on to say that Molecule's driver passes the string through to
the daemon, so what works for `docker pull` is what the driver gets. It does
not: the driver reuses `image:` as a tag it constructs, and the combined form
fails at `create` for that reason — not because the reference is malformed.
Decision 2a records what actually happens and what it costs. The combined form
is still the right one to write; it just needed `pre_build_image: true` beside
it, which is a fact about the driver rather than about the reference.

*Alternative considered:* the bare `repo@sha256:…` form. Unambiguous, but
strictly less legible for no gain — the tag carries no authority in the
combined form, so it cannot mislead the resolver, only inform the reader.

*Fallback, decided in advance rather than improvised mid-build:* what was
verified is `docker pull`, and Molecule reaches the daemon through
`community.docker`, whose reference parsing was not what that command
exercised. If the driver rejects the combined form — the failure is immediate
and unmistakable, every scenario failing at `create` — the pin becomes the bare
`repo@sha256:…` and the tag moves into the adjacent comment task 3.2 already
adds. That is a formatting fallback, not a different decision: the digest, the
manifest-list choice and everything the delta requires are unchanged either
way, so taking it needs no return to this plan.

*Outcome:* the fallback was **not** taken. `create` did fail, but on the tag
construction described in decision 2a rather than on the reference form, and
the bare form would have failed identically. The combined form stands, and the
derived tests accept either — so this remains a live fallback for anyone who
later needs it, not a road already travelled.

### 2. Pin the manifest-list digest, not the amd64 digest

`sha256:0172e3b586fc316491b5ac080e6b24c5f66cde985c27c625025f13f66a8cd21f` is
the manifest list. Each architecture still resolves to its own image beneath
it, so an arm64 developer machine and an amd64 runner both work while pinning
one identical, immutable object.

*Alternative considered:* pinning the amd64 image digest directly. Marginally
stricter — it names the exact bytes CI runs — but it would break the suite
outright on an arm64 machine, and "the developer cannot run the suite at all"
is a worse failure than "the developer's architecture differs from CI's", which
was already true under `:latest`.

### 3. The pin is repeated inline in all eight `molecule.yml` files

Molecule supports a shared base configuration at `.config/molecule/config.yml`
that every scenario inherits, and moving the `platforms:` stanza there would
give the pin a single home.

Not done. Each scenario's `platforms:` block is currently self-contained and
carries scenario-specific commentary explaining why *that* scenario needs
`privileged: true` (the reasons differ between roles — systemd for `docker` and
`hardening`, `CAP_SYS_ADMIN` for `platform_data_volume`). Splitting the stanza
across two files would put half of each scenario's definition somewhere the
scenario does not mention, for a change whose subject is making the suite's
result trustworthy rather than reorganising it.

The duplication's real cost is drift — eight copies, one updated. The derived
test removes that cost: it asserts not only that each is pinned but that
scenarios naming the same image repository name the **same** digest, so a
partial refresh fails the required check.

That constraint is stated in the delta requirement, not only here. A required
status check that enforces a rule recorded solely in an archived change's
`design.md` gives a later contributor nothing to appeal to — and this
particular rule is what justified rejecting the shared-`config.yml`
alternative, so it cannot live outside the specification. It is scoped to
*same repository, same digest* rather than *one digest everywhere*, so a future
scenario that legitimately needs a different base image (a Debian-based role,
say) is not blocked by a rule written for a drift problem it does not have.

### 2a. The pin forces `pre_build_image: true`, discovered during implementation

Planned as a one-line edit per scenario; it is not. The Docker driver reuses
`image:` as the *tag* of an image it builds locally —
`molecule_local/{{ item.image }}`, at `create.yml:109` and `:146` of
`molecule_plugins/docker/playbooks/` — and a digest reference cannot be a tag.
With the digest in `image:` and the build step active, `create` fails trying to
pull `molecule_local/geerlingguy/docker-ubuntu2204-ansible:latest:sha256:0172…`,
having split the reference on its last colon. Observed, not predicted.

`pre_build_image: true` skips the build and runs the named image directly
(`create.yml:58`, `:71`, `:86`, `:99`), which is what makes the digest usable.
No scenario in this repository set it before; none carries a custom
`Dockerfile.j2` either, so all eight were running the driver's default template.

That template is the part worth knowing about. It is `FROM {{ item.image }}`
followed by `apt-get update && apt-get install -y python3 sudo bash
ca-certificates iproute2 python3-apt aptitude rsync`, executed at container
build time on every `molecule create`. **So the suite was never reproducible,
and pinning the base image alone would not have made it so** — each run
installed whatever those packages resolved to that day. Adopting
`pre_build_image: true` removes that layer, which means this change pins the
whole container rather than only its base, and the suite stops reaching the
Ubuntu archives during `create` at all. That is a larger gain than the change
set out to make, and it arrives as a consequence rather than as scope added.

What it costs: the container no longer gets `aptitude` and `rsync`, the only two
of that list absent from the pinned image (verified with `dpkg-query` against
the digest; the other six are present). Nothing in `ansible/roles/`, in the
pinned `geerlingguy.docker` role, or in `ansible/playbooks/` uses
`ansible.posix.synchronize`, `aptitude`, or an apt `upgrade:` — the three things
that would need them. Verified by search before adopting, not assumed.

*Alternative considered:* keeping the build layer and pinning the base in a
per-scenario `Dockerfile.j2` whose `FROM` carries the digest, leaving `image:`
as the tag-shaped string the driver wants. It preserves today's behaviour
exactly. Rejected: the pin would then live outside `molecule.yml`, where the
delta requires the platform image to be declared by digest and where the derived
test reads it — so it would need a spec change to permit, and it would keep the
unpinned `apt-get` layer this project's conventions object to anyway.

### 3a. The check's discovery is bounded by `ansible/requirements.yml`

`ansible/roles/` holds this repository's roles and, once provisioned, the
pinned Galaxy role installed beside them — which ships a scenario of its own,
on a floating env-interpolated tag (see Context). An unbounded glob would
therefore make the required check demand a pin on a file that is gitignored,
discarded on the next `ansible-galaxy install`, and not this project's to
author; and it would return different results in CI and locally, which is the
failure class this repository has already been bitten by.

The exclusion is derived by reading `ansible/requirements.yml`'s `roles:` list
and skipping directories whose names appear in it. PyYAML is already a pinned
dependency of that suite and already used to parse workflow YAML, so this adds
no dependency.

**How an entry resolves to a directory name.** `ansible-galaxy` names the
install directory from `name` where the entry gives one, and otherwise from the
`src` basename with any `.git` suffix and version qualifier stripped. The check
resolves entries the same way. An entry it cannot resolve to a name, and an
`ansible/requirements.yml` that is missing or unparseable, SHALL fail the check
identifying the entry or the file — never yield an empty or partial exclusion
set. The two directions are not symmetric: a too-narrow exclusion produces a
false failure that someone investigates, while a silently widened one lets an
unpinned scenario through, which is the vacuous pass this capability forbids
elsewhere. Today the manifest has a single `roles:` entry, in `name` form; this
rule is for the entry someone adds later.

*Alternative considered:* excluding directory names containing a `.`, the
Galaxy `namespace.role` convention. Cheaper, but it encodes a naming habit
rather than a fact, and it would silently exempt a hand-vendored directory that
happened to be named that way.

*Alternative considered:* restricting to git-tracked files via `git ls-files`.
Precise, and it would work — but it makes the check's answer depend on what is
staged rather than on what is pinned, and it introduces an external binary into
a suite whose existing tests assert it needs no container runtime and no
Terraform binary. The deciding ground is the next paragraph, not that: `git
ls-files` excludes *everything* untracked, which is the unsafe direction.

The manifest-derived rule has a property the other two lack: content vendored
into `ansible/roles/` that is **not** pinned in `ansible/requirements.yml` is
not excluded, and its scenarios are held to the pinning obligation. That is the
correct answer under this project's conventions — unpinned external content has
no business there — so the boundary fails in the safe direction.

**The suite already contains the rejected heuristic, and it stays.**
`.github/tests/test_ci_configuration.py`'s existing `role_names()` helper
excludes directory names containing a `.`, and `roles_with_molecule_scenarios()`
builds on it; both serve the pre-existing tests about `ansible-verify.yml`'s
role discovery. Those tests are not this change's to edit, and rewriting a
passing helper to reach a boundary the new checks can establish for themselves
would put unrelated assertions at risk for a tidiness gain.

So the file will carry two exclusion rules with different strengths. That is
stated here rather than left for a reader to trip over: the new checks use the
manifest-derived rule because they gate a pinning obligation and must fail safe;
the older helper's weaker rule is adequate for what it does. Unifying them is
worth doing and is not done here — it edits existing tests, which is a
different change.

### 4. The derived test lives in `.github/tests/`, and no second spec delta is needed for that

`iac-cicd-pipeline`'s *The Continuous-Integration Configuration Is Itself
Verified* requirement already names "which versions are pinned where" as
something the executable suite SHALL assert. A container image pinned in a
committed file, consumed by a pipeline job, is that. No delta is required to
make this test's home legitimate.

What does need a wording update is `AGENTS.md`'s Testing table, whose "Subject"
column currently reads "CI configuration — workflows, `dependabot.yml`,
`.pre-commit-config.yaml`". A future test author dispatched with that table
would conclude there is nowhere to put a static assertion over a
`molecule.yml`, and would report the gap rather than invent a destination —
which is the correct behaviour and the reason to widen the column now. That is
a project-conventions edit, not a spec change.

The test must respect the suite's own standing constraints, which are
themselves asserted by existing tests in that file: standard library plus
manifest-pinned dependencies only, no network, no container runtime. Reading
committed YAML satisfies all three.

### 5. Guard the name comparison; keep both accepted forms

The fix is:

```yaml
- (item.stat.pw_name | default('')) == item.item.owner or (item.stat.uid | string) == item.item.owner
```

and the same shape for `gr_name`/`gid`. `default('')` makes the left operand
defined in every case, so evaluation reaches the uid comparison that was always
the branch capable of passing.

*Alternative considered:* dropping the name branch entirely and comparing on
uid/gid alone. It would be simpler, and every declared owner in this repository
today is a numeric string. But `platform_data_volume`'s README documents
`owner`/`group` without constraining them to numeric ids, and the role passes
them straight to `ansible.builtin.file`, which accepts a name. Removing the
branch would narrow what the role's variable interface accepts as a side effect
of fixing a test — the kind of quiet contract change this project's conventions
exist to prevent.

*Alternative considered:* reordering the operands so the always-defined uid
comparison is evaluated first. Jinja's `or` does short-circuit, so this works —
and it works by accident of evaluation order, leaving a latent raise for
whoever later reorders the two back. The explicit guard states the intent.

## Risks / Trade-offs

**A hand-pinned digest has no refresh mechanism and will age indefinitely** →
Accepted, and recorded in `docs/deferred-work.md` rather than solved.
Dependabot's `docker` ecosystem scans Dockerfiles and Compose files, not
`molecule.yml`, so it will not see this pin; a bespoke refresh workflow is out
of proportion to a test-only base image. The trade this makes is deliberate: a
known-stale image the suite runs against reproducibly is worth more than a
current one it cannot make the same claim about twice. Decision 3's
same-digest-per-repository assertion keeps the manual refresh to a single
find-and-replace. Revisit if the pinned image ages far enough that a scenario
fails for a reason traceable to the base image rather than to the role.

**The pinned digest could be deleted upstream, breaking every scenario at
once** → Low, and loud rather than silent: `docker pull` fails with a clear
message and the suite fails to create a container, rather than testing
something unexpected. The recovery is the same one-line refresh.

**The suite may reveal further failures once it runs green-adjacent** → Only
one scenario is known to fail, on two independent runs with identical results,
so the failure set is not suspected of being larger. But this change's
verification is a full local `molecule test --all` across all five roles, and
if a second failure surfaces it is either fixed here (if it is the same class)
or recorded as its own change (if it is not) rather than folded in silently.

**Pinning changes what the suite runs against, and could itself turn a passing
scenario red** → This is the point of doing the pin and the assertion fix in
one change rather than two: the assertion is fixed against, and observed
against, the image the suite will actually keep running. A scenario that breaks
under the pin was already broken under whichever `latest` it last happened to
pull.

## Relationship to `fix-volume-discovery-and-consistency`

That change is opened on its own branch with a handoff and no proposal, and it
targets the same role: an unreachable `assert` in
`ansible/roles/platform_data_volume/tasks/main.yml`, plus consistency slips
elsewhere. Its handoff explicitly directs whoever takes it up to check whether
`ansible/roles/platform_data_volume/molecule/default/` can already exercise the
empty-`find` path before adding a scenario.

The two are **disjoint in the files they edit**: that change touches the role's
`tasks/main.yml` (and, if it adds coverage, a new or extended scenario); this
one touches `verify.yml`'s ownership assertion and eight `molecule.yml` image
lines. Neither depends on the other's outcome.

They are **ordered by preference, not by requirement**: this change should land
first, so that change begins from a suite that is green and pinned, and any red
it then sees is attributable to its own work. If it lands first instead,
nothing here breaks — the only consequence is that whichever scenario it adds
must carry a digest-pinned image, which this change's derived test will require
of it.

Recorded here rather than in `docs/change-queue.md` because it concerns a
change already opened, and this change does not wait on it.

## Migration Plan

None. No production infrastructure, no deployed service, and no role behaviour
changes; nothing to roll back beyond reverting the commit. The Compose stack is
untouched, so merging this triggers no `platform-deploy.yml` run.

## Local verification results

Recorded here because task 6.1 requires them to be kept as **local** results.
They are deliberately not entered in `docs/change-queue.md` entry 4's baseline
table, which asks for runs on pull requests: a developer machine cannot answer
the question that table exists to answer. Entry 4's third data point comes from
this branch's own `ansible-verify.yml` run (task 6.5).

All eight scenarios pass, across all five roles carrying them. CI durations from
`docs/change-queue.md` entry 4 are shown only to make the comparison legible —
different machine, different conditions.

| Role | Scenarios | Local | CI, before this change |
|---|---|---|---|
| `deploy_user` | 3 | 25m41s | 6m33s |
| `docker` | 1 | 1m34s | 2m41s |
| `hardening` | 1 | 1m38s | 2m36s |
| `ops_user` | 2 | 16m33s | 4m42s |
| `platform_data_volume` | 1 | pass | **fail**, 2m07s |

Two observations worth keeping, neither of them a claim about CI:

- `docker` and `hardening` completed faster here than they did on a hosted
  runner beforehand, on a machine that is otherwise several times slower on the
  other roles. That is consistent with decision 2a removing an `apt-get update`
  plus eight-package install from every `create`, and inconsistent with it being
  noise.
- `deploy_user` and `ops_user` remain slow locally. Both spend that time in
  scenarios that exercise registry-login failure paths and their retries; the
  ratio to CI is what this machine does to everything, not something this change
  introduced.

Alongside: the CI-configuration suite passes at 68 tests, and
`pre-commit run --all-files` passes every hook — `terraform fmt`, `tflint`,
`terraform validate`, `gitleaks`, `ansible-lint`, `ansible-playbook
--syntax-check`. `tflint` had to be installed to get a real result from that
hook rather than an error; before that it was failing on absence, not on
content.
