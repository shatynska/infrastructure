# Design

## Decision 1: what counts as a scenario reading the controller, and the sweep that establishes it

What a scenario reads is a fact about scenario text. The safety case for every exclusion below rests on one sweep, so the sweep's signal is stated before its result — and it is stated broadly, because the first attempt at this design used a narrow one and missed two live cases in this repository.

**The criterion is that a scenario reads a repository file from the controller** — not that it touches the controller at all. The distinction is what keeps the signal usable. Scenario text is dominated by tasks that read the *managed node*: roughly twenty `ansible.builtin.slurp` tasks read absolute paths like `/home/ops-claude/.ssh/authorized_keys` inside the container, and several delegated tasks derive facts from values already registered without opening a file. Neither class can be affected by a path filter over this repository, so neither is in scope; folding them in would make the standing check this design requires (see Risk, below) red on day one against sites nothing could bless meaningfully.

**A repository read reaches the controller by more than one route**, and `delegate_to: localhost` names only some of them:

- a **file-reading lookup** — `lookup('file' | 'template' | 'fileglob' | 'ini' | 'csvfile' | 'first_found' | 'unvault', …)` — which executes on the controller **whether or not** the task carrying it is delegated;
- **controller-resolved inclusion of variables**: `vars_files`, `include_vars`, and `include_role`'s `vars_from` — in the list form *and* the mapping form (`include_vars:` with `file:` or `dir:` beneath it), which reach the same files;
- **controller-resolved inclusion of tasks or plays**: `import_playbook`, `include_tasks`, `import_tasks`, and `include_role`'s `tasks_from`. This route is the one the round-3 review found missing, and it is not hypothetical — `platform_data_volume/molecule/multiple-devices-reverse-order/` uses `import_playbook` three times to read its sibling scenario's `converge.yml`, `prepare.yml` and `verify.yml`. It is also the route by which a future scenario would most plausibly read `ansible/playbooks/**`, which is an excluded path;
- **a source path on any module that sends a file to the managed node** — `copy`, `template`, `script`, `unarchive`, `assemble` — which is a controller path unless the module declares otherwise (`remote_src`);
- **a path argument on a task that runs on the controller**, which is where a delegated `slurp`, `fetch`, `shell` or `command` belongs. `delegate_to: localhost` is the spelling this repository uses and is not the only one: `delegate_to: 127.0.0.1`, `connection: local` and `local_action:` put a task there too, and a check matching the first literally lets the others carry a read of an excluded path straight past it. An undelegated `slurp` reads the managed node and is out of scope by construction: `slurp` has no `remote_src` option at all, so "unless `remote_src`" is not the discriminator for it — delegation is;
- **a path declared anywhere in a scenario's `molecule.yml`** — its provisioner `env:`, and its `dependency.options` — which is neither a task nor a play. Both spellings are live here, and the second was found by the test author rather than by either sweep: every authored scenario declares `requirements-file: ../../../../requirements.yml`, which Molecule resolves on the controller before any play runs.

**Every one of these is recognised in its collection-qualified spelling as well as its bare one.** `ansible.builtin.import_playbook:` is the same route as `import_playbook:`, and the qualified form is what `ansible-lint`'s own `fqcn` rule pushes authors toward — so a check reading only the bare spelling would be blind to the form this repository is being nudged into writing, on the route most likely to reach the excluded playbook directory. Code review found exactly that gap after the first implementation passed.

**A scenario's own configuration file is not read by an enumerated key list either.** `provisioner.playbooks.*` and `provisioner.inventory.links.*` are documented Molecule options naming controller paths, and the second is literally how a scenario would come to read `ansible/inventory/` — the flagship excluded path. So every scalar in `molecule.yml` that *navigates* — carrying `../`, or a leading `./` or `/` where a variable stood — is treated as a read unless it is permitted. Navigation is the discriminator rather than the presence of a slash: `platforms.image` is a registry reference and `platforms.name` carries a slash only inside a `${VAR:-default}` fallback, and reporting those would make the check red on every scenario with nothing meaningful to permit.

**And the list closes by refusing, not by passing over.** Enumerating routes has the same staleness problem Decision 2 identifies in enumerating paths, and the same answer: where the check meets a construction it does not recognise carrying a repository-resolvable path — an unfamiliar lookup name, a module it has no rule for — it SHALL refuse rather than ignore. Adding a route is then a visible edit; missing one is not silent. This costs nothing today, because the table below establishes that no such construction exists in the tree, and the criterion above already keeps the noisy class — reads of the managed node — out by construction. Breadth *within* the controller class is free; breadth across the boundary is what would have made the check unusable.

The first sweep looked for `delegate_to: localhost` *combined with* the path spelling `{{ playbook_dir }}/../..`, and that conjunction is what failed. `ansible/roles/docker/molecule/default/verify.yml:92` reads `ansible/requirements.yml` through `lookup('file', playbook_dir + '/../../../../requirements.yml')` — string concatenation rather than interpolation, so the path pattern missed it — and `ansible/roles/swap/molecule/default/verify.yml:71` reads its own role's `defaults/main.yml` the same way. Both are delegated, so the delegation half of the signal was sound and the path half was not; but a `lookup()` needs no delegation at all, so the route list above is what the standing check must be built on rather than the one that happens to catch today's cases.

**The corrected result.** Fourteen entries cover every read of a repository file from the controller across this repository's seventeen authored scenarios — twelve individual sites, plus two declarations each repeated in every scenario. None of them reads any path this change excludes:

Line numbers below locate each read **as of the sweep** and are descriptive only. They are not how the standing check identifies a read — Decision 1a says what is, and why.

| Site | Reads | Class |
|---|---|---|
| `deploy_user/molecule/default/verify.yml:419` | the repository root | **relocates** (Decision 4) |
| `deploy_user/molecule/default/verify.yml:457` | the repository root | **relocates** |
| `ops_user/molecule/default/verify.yml:631` | `ansible/inventory/` | **relocates** |
| `deploy_user/molecule/default/verify.yml:563` | its own role directory | role-local; stays |
| `ops_user/molecule/default/verify.yml:618` | its own role directory | role-local; stays |
| `ops_user/molecule/default/verify.yml:666` | its own role's `README.md`, by a delegated `slurp` | role-local; stays |
| `ops_user/molecule/revocation-steady-state/verify.yml:59` | its own scenario directory, running a nested `ansible-playbook` | role-local; stays |
| `swap/molecule/default/verify.yml:71` | its own role's `defaults/main.yml` | role-local; stays |
| `platform_data_volume/molecule/multiple-devices-reverse-order/converge.yml:8` | its sibling scenario's `converge.yml`, by `import_playbook` | role-local; stays |
| `platform_data_volume/molecule/multiple-devices-reverse-order/prepare.yml:8` | its sibling scenario's `prepare.yml`, by `import_playbook` | role-local; stays |
| `platform_data_volume/molecule/multiple-devices-reverse-order/verify.yml:8` | its sibling scenario's `verify.yml`, by `import_playbook` | role-local; stays |
| `docker/molecule/default/verify.yml:92` | `ansible/requirements.yml` | escapes the role directory; **its target is a trigger** |
| every authored `molecule.yml`, `ANSIBLE_ROLES_PATH` | `ansible/roles/` | escapes the role directory; **its target is a trigger** |
| every authored `molecule.yml`, `dependency.options.requirements-file` | `ansible/requirements.yml` | escapes the role directory; **its target is a trigger** |

The last three rows are why the exclusions hold rather than a threat to them: `ansible/requirements.yml` and `ansible/roles/` both remain triggers. The three `import_playbook` rows arrived with the route that found them, and they are the evidence for adding it rather than a decoration on it — a check built without that route would have passed a scenario reading three repository files.

**The `requirements-file` row arrived later still, and from neither sweep.** The test author derived tests from the delta, went to `molecule.yml` to do it, and found the declaration in all seventeen authored scenarios. Two sweeps had read those files for `ANSIBLE_ROLES_PATH` and not seen it. Nothing about the exclusions is endangered — the target is a trigger, as the row says — but a premise check closing by refusal would have been red on seventeen sites on the day it landed, and the cheap escape from that is exactly the unstated narrowing this design already went wrong by once. It is recorded here with its provenance because it is the third demonstration of the same lesson: the enumeration is what this mechanism is, and it is harder to complete than it looks.

**Three classes sit deliberately outside the table**, named here so the next sweep does not re-litigate them:

- **Undelegated `slurp` and every other read of the managed node.** Out of scope by the criterion; roughly twenty sites.
- **Delegated tasks that open no file** — `docker/molecule/default/verify.yml:99` and `:105` parse and select over an already-registered fact, and `swap/molecule/default/verify.yml:80` asserts over one. They run on the controller and read nothing from the repository.
- **`image_prune/molecule/default/prepare.yml:58`**, which runs `docker pull` and `docker save` into `/tmp` on the controller. It touches the controller heavily and reads no repository file, which is exactly why "touches the controller" was the wrong criterion.

## Decision 1a: the permitted set is keyed by file, construction and target, counted — never by line offset

The table above locates each read by `file:line`, because that is how a sweep reports. The standing check must not key on it, and the reason is immediate rather than theoretical: **this change's own section 1 deletes three tasks from two of the files the table names.** `deploy_user/molecule/default/verify.yml` loses the tasks at `:419` and `:457`, and `ops_user/molecule/default/verify.yml` loses the one at `:631` — so the permitted reads surviving *below* those deletions, `deploy_user:563` and `ops_user:666`, sit at different offsets the moment the relocation lands. A check keyed on offsets is wrong on the commit that introduces it, and wrong in both directions: it reports the surviving role-local scans as unpermitted, and it permits whatever text has slid onto the recorded numbers.

So a permitted read is identified by **the file that holds it, the construction that performs it, and the target that construction resolves to** — for instance "in `ops_user/molecule/default/verify.yml`, a delegated `slurp` whose `src` resolves to the role's own `README.md`". That identity survives any edit that does not change the read itself, which is what a permitted set has to do to stay true.

**Keyed by read, not by path.** The alternative reading — enumerate the permitted *paths* and allow any read that stays inside them — is weaker in exactly the way this check exists to prevent. A scenario adding a second read of `ansible/requirements.yml` would pass without anyone looking at it, and the point of the enumeration is that a read added later is considered rather than inherited. The refusal is over reads; the paths are what each permitted read is permitted to reach.

**And the enumeration carries a count, because the identity alone does not separate one read from two.** The example just given is the awkward case for this key rather than a comfortable one: the natural place to add a second read of `ansible/requirements.yml` is `docker/molecule/default/verify.yml`, where the permitted read already lives — same file, same construction, same target. Under plain set membership the duplicate matches the permitted entry and passes unexamined, which satisfies the letter of the key while defeating the obligation it was written for. So each entry records **how many occurrences are expected**, and a file carrying more than its entry allows fails exactly as an unenumerated read does. Today every count is one.

A count is the cheapest discriminator that keeps what this decision bought. The alternative — keying additionally on something inside the read, its task `name:` or the literal text of its expression — discriminates duplicates too, but reintroduces the fragility the whole decision exists to remove: renaming a task or reformatting a lookup would invalidate the entry, which is the line-offset problem wearing different clothes. Take the count; reach for an in-file discriminator only if counting proves insufficient.

**Comments and asserted strings are not reads, and the distinction is where a careless sweep goes wrong in the dangerous direction.** Scenario text mentions `inventory/`, `group_vars/`, `playbooks/` and `ansible.cfg` several dozen times; every one of those is a comment or an expected-failure substring. `hardening`'s `absent-ssh-cidrs` scenario asserts that a failure message contains the literal `ansible/inventory/group_vars/<environment>.yml` — an assertion about a string, not a file opened.

**The exclusions.** Four narrow paths, each justified by the table above rather than by what its directory is called:

| Excluded | Why it is safe |
|---|---|
| `ansible/inventory/**` | Reached by exactly one site, which Decision 4 moves to `.github/tests`, where it runs on every pull request rather than on a subset |
| `ansible/playbooks/**` | Reached by nothing. Named in one comment, in `ops_user/molecule/default/converge.yml`, recording that the scenario's role ordering mirrors the playbook's — and the mirroring is not asserted |
| `ansible/requirements.txt` | Added by `apply-host-configuration-through-a-gated-workflow` for the converge workflow's own `ansible-core`. Distinct from `ansible/requirements-test.txt` and `ansible/requirements.yml`, both of which remain triggers, the second of them read directly by `docker`'s scenario |
| `ansible/.envrc*` | Operator environment scaffolding. `.envrc` is gitignored; `.envrc.example` is a document |

`ansible/ansible.cfg` is deliberately **not** excluded, and the reason is worth recording because two scenario comments assert the opposite of what is true. `platform_data_volume`'s prepare plays both say the project's `ansible.cfg` "sets no `fact_caching` backend", as though the scenario ran under it. It does not: Molecule runs with the role directory as its working directory, so Ansible's configuration discovery finds no `ansible.cfg` there and never reaches `ansible/ansible.cfg` two levels up. Those comments are wrong today and this change does not correct them — but a file the scenarios believe governs them is not one to exclude on the strength of a sweep, and it changes rarely, so keeping it a trigger costs nothing.

## Decision 2: exclusion polarity, so that a new path fails safe

The filter is written as `ansible/**` followed by negations, not as a list of the paths that should run the suite.

The two spellings agree on today's tree and disagree on tomorrow's. A file added under `ansible/` that nobody thought about is, under an inclusion list, silently not a trigger — the suite skips and the gate reports green, which is this pipeline's defining failure mode and the thing its own workflow comments are written to prevent. Under an exclusion list the same file runs the suite: wasteful, visible, and correctable by a one-line commit. The wasteful direction is the recoverable one.

This mirrors the polarity argument already made in `ansible-verify.yml`'s resolution step, which refuses an unresolvable filter result rather than reading it as "nothing changed", and in this capability's discovery, which fails on an empty role set rather than concluding success having run nothing.

## Decision 3: negation is `dorny/paths-filter`'s, and only its declaration is statically checkable

`dorny/paths-filter` matches with picomatch and supports `!` patterns within a filter — **but only under a quantifier that is not its default, and getting this wrong inverts the change.** The action's `predicate-quantifier` defaults to `some`, under which every pattern is compiled independently and OR-ed (`patterns.some(rule => rule.isMatch(filename))`), and picomatch *inverts* a matcher built from a `!`-prefixed pattern. A negation therefore matches every path it does not name, the OR is true for nearly every file in the repository, and the filter selects `README.md` and `terraform/*.tf`. The four exclusions would be inert and the suite would start seven containers on every pull request — strictly more expensive than the `ansible/**` this change replaces, on the required check whose degraded runs prompted it.

`some-with-excludes` is the quantifier that means what the list reads as: selected where some positive matches and no negation does. It is **order-independent**, so the positive is written first for legibility rather than for semantics — an earlier draft of this design claimed the order was load-bearing, which is false for this action and would have left the next editor reasoning from the wrong constraint. Exclusion is final: no later pattern re-includes a file.

This was found in code review, after the filter had been written and every assertion over it was green. That is the point worth keeping: every check in this repository reads the *declared patterns*, and the declaration was correct — what was wrong was an input none of them read. `.github/tests` now asserts the quantifier itself, because a filter whose negations are silently inert is the "economical and silent" failure Decision 2 exists to refuse, arriving through the mechanism chosen to implement it.

`.github/tests` can assert **what the filter declares**: that the `ansible/**` positive is present, that each of the four negations is present, that no negation was added that this design did not establish, and — the one that matters most — that `predicate-quantifier: some-with-excludes` is declared alongside them. It cannot assert what the action *does* with those patterns, because reproducing picomatch would need a dependency the suite is forbidden from taking, and running the action would need a network call it is forbidden from making. Those constraints are themselves asserted by tests in that module.

One qualification, added after review. The suite does carry a **deliberately approximate** matcher over the declared patterns — Section 2's revision of the existing selection test needs one, to assert that the excluded paths are not selected rather than merely that the negations are declared. That matcher is an approximation of picomatch written here, not authority on what the action does: where the two disagree the action wins, and the observation below is what establishes the behaviour. It is worth having anyway, because it is the only thing that can go red when someone deletes a negation.

So the behaviour is established by observation on real pull requests, and the two directions are not equally available to this change:

- **The suite still runs where it should.** This change's own pull request touches `ansible/roles/deploy_user/molecule/default/verify.yml` and `ansible/roles/ops_user/molecule/default/verify.yml`, so it must select the suite. Observable on this change's first pull request.
- **The suite skips where it should.** Needs a pull request whose whole `ansible/` footprint is excluded paths. This change cannot produce one, so it is the `ship:confirm` observation and it is made on the next such pull request rather than on this change's own.

That asymmetry is stated rather than worked around. A filter that over-matches is invisible until someone notices the bill; a filter that under-matches is invisible until something breaks in production. This change's own pull request proves the direction whose failure is silent.

## Decision 4: the relocated scans keep their assertions and change their home

Three sites move. What each asserts is fixed; where it runs, when it runs, and how it reports change.

**The GitHub/GHCR token-marker scan.** A `grep -rlE` for `gh[pousr]_[A-Za-z0-9]{20,}` and `github_pat_[A-Za-z0-9_]{20,}`, rooted at the repository. Straightforward to reimplement as a walk over the file set Decision 5 fixes.

**The `ghcr_pull_token` literal scan.** This one has a property that will be lost by anyone reimplementing it casually, and its own comment says so: *"A line-oriented grep cannot do this correctly: both scenario converge files assign the token as a YAML FOLDED scalar, so the assignment line is just `ghcr_pull_token: >-` and the lookup that makes it acceptable sits on the following lines."* It matches the assignment, absorbs every following line indented deeper than the assignment, and accepts the value only if the absorbed block is an inline `!vault` value or a `lookup('env', ...)` expression. It is already Python; it moves nearly as-is.

Its comment also records why it does not exclude the two scenario files by path — *"it would blind the scan permanently in exactly the files most likely to acquire a pasted real token, since running the credentialled verification means having a live token at the keyboard while editing them"*. That reasoning survives the move unchanged and is carried across with it.

**The operator private-key scan, widened from `ansible/inventory/` to the repository.** A search for `-----BEGIN (OPENSSH |RSA )?PRIVATE KEY-----`, with the pattern assembled from two halves at run time so it does not appear literally in the file that searches for it — otherwise the scan matches its own text. In `.github/tests` the same problem exists and has the same solution; it is not an artefact of the old home.

The widening is the point rather than a convenience. The scan's own comment calls its root DERIVED — *"no scenario names that path, but it is where `ops_user_accounts` and therefore the committed key material actually lives"* — which is an argument for scanning where the risk is, and the risk is not confined to one directory. `proposal.md` argues that a repository-scope claim held behind a directory trigger claims a scope its trigger does not give it; the same holds for a scan rooted at one directory while its siblings scan the repository. Widening also makes the two modified requirements agree on one predicate instead of two, and costs nothing: the token scans already establish the walk.

Only the escaping sites move. `deploy_user`'s and `ops_user`'s key scans over their own role directories stay, because a change to those directories selects the suite anyway.

**What is deliberately not preserved: the scenario boundary.** These assertions trace to two scenarios in `openspec/specs/iac-host-configuration/spec.md` — *GHCR token is never committed*, under the *Host Authenticates to GHCR for Application Image Pulls* requirement, and *Operator private keys are never committed*, under *Unprivileged Operator Accounts Support Interactive Host Inspection*. Neither scenario names a verification mechanism, and the word "Molecule" appears nowhere in that specification; both say the secret SHALL NOT appear in plaintext anywhere in the repository. The move puts the verification where "anywhere in the repository" is actually reachable. That is why this change's delta is against `iac-cicd-pipeline` and not against `iac-host-configuration`: what the repository requires is unchanged, and what checks it is a pipeline concern.

## Decision 5: the relocated scans read tracked files, via `git ls-files`

The old home made this question invisible. A scan running inside a Molecule verify play ran on a developer's machine only when they chose to run that scenario, and in CI only against a fresh `actions/checkout`. `.github/tests` runs on **every** pull request and on every developer's `python3 -m unittest discover --start-directory .github/tests`, against whatever that working tree holds.

What a repository root holds on a developer's machine is not what it holds in CI. In this repository it holds `.molecule-home/`, `.terraform/` directories, virtualenvs, the gitignored `ansible/.envrc` — which is where `MOLECULE_GHCR_PULL_TOKEN` is read from, so it plausibly holds a real token — and, from the main checkout, every sibling working tree under `.claude/worktrees/`. A naive walk fails on all of them, and the natural remedy is a path-exclusion list, which is the permanent blinding Decision 4 quotes the original author refusing.

So the file set is **tracked files, from `git ls-files`**, which is also what `AGENTS.md` says this suite's subject is: "a static read of a **committed** file". An uncommitted token is not a committed secret, and the check that should catch it before it becomes one is `gitleaks`, which `pre-commit` already runs on `git commit` and which CI runs on the pull request.

Two consequences are accepted rather than hidden:

- **It spawns a subprocess.** The suite's stated dependency limit forbids a network call, a credential, a container runtime and a Terraform binary; `git` is none of those, and the module already reaches for external tools through a guarded helper for the bash-bodied gate tests. The delta states the admission explicitly rather than leaving it inferred.
- **A missing `git` SHALL fail, not skip.** This is the one place the existing helper's pattern must not be copied. `AGENTS.md` warns that verification which cannot reach what it needs "skips and reports success rather than failing", and for a secret scan a skip is a hole that reports green. CI always has `git`, having checked the repository out with it; a machine without it should hear so.

Two edge cases follow from reading a list of paths rather than walking what exists, and both are decided here rather than left to the implementer:

- **Matching is over bytes.** The patterns are ASCII and the markers they look for are ASCII; decoding every tracked file as text would make an undecodable file — none is tracked today, and nothing prevents one — a hard failure that examined nothing, which is the shape this decision exists to prevent reached from the other side. Read bytes, match bytes.
- **A tracked path absent from the working tree fails**, naming the path. This suite's subject is the committed tree, and a partial checkout cannot establish a property over it; a sparse or interrupted checkout is a state to hear about rather than to scan around. It is the same argument as the enumeration failing, one level down.

## Decision 6: nothing about the gate's structure changes

Worth stating, because the obvious worry is that narrowing the trigger disturbs the three-way distinction the gate makes, and it does not.

```
discover (always runs, no `if:`)
  ├── roles       ← every role carrying scenarios; fails loudly if empty
  └── run-suite   ← the filter's verdict on this diff
                      ▲
                      └── THIS is the only thing this change edits

molecule   if: run-suite == 'true',  matrix: roles
ansible-verify (if: always())
  ├── discover failed            → fail
  ├── matrix skipped, suite owed → fail
  ├── matrix skipped, not owed   → success
  └── matrix success             → success
```

`roles` and `run-suite` are already independent: discovery's vacuity refusal is computed unconditionally and the gate reads `DISCOVER_RESULT` before anything else, precisely so that a discovery failure cannot be laundered through the "nothing changed" branch. Narrowing the filter changes which diffs land in the third row. It does not add a row, remove one, or make any row reachable that was not.

One text change follows from it. The third row's message currently reads *"Nothing under the configuration directory changed, so the suite was skipped"*, which becomes false: something under `ansible/` may well have changed and been excluded. The message must say what is now true — that nothing the suite reads changed — or it will mislead exactly the reader who is trying to work out why the suite did not run. The gate body is executed standalone by `.github/tests`, so this lands there too.

## Risk: the excluded set goes stale

The failure is specific and quiet. Someone adds a scenario that reads `ansible/inventory/`, or moves a playbook into a place a scenario consumes, and the filter keeps excluding a path that is now read. The suite skips, the gate reports green, and nothing observes the gap.

Three things bound it, and only the third would actually catch the case:

- The exclusion is four named paths rather than a wildcard, so widening it is a deliberate edit to a file `.github/tests` asserts about.
- The sweep that produced Decision 1's table is repeatable in about a minute and its signal is written down, so the next person runs the widened one rather than reinventing the narrow one.
- **A standing check over scenario text, built on Decision 1's criterion and route list.** Any controller-side read of a repository file in an authored scenario that is not in Decision 1's table fails the pipeline's own configuration checks. This is a static read of committed files, so it belongs in `.github/tests` and is in scope for it.

The third is the answer and this change writes it. It is not a test of the filter — a filter can be perfectly correct about a premise that has stopped being true — it is a test of the premise. Note what it costs: after the three relocations, nine sites plus two per-scenario declarations must be permitted explicitly, or the check is red on day one — and "day one" is not rhetorical, since the `requirements-file` declaration would have made it red on seventeen sites had the test author not found it. That is the correct direction by Decision 2's own polarity argument: a blessed-list edit is visible and cheap, a missed read is silent.

Note also what the criterion buys, which is the difference between a check that can go green and one that cannot. Written against "touches the controller" it would fire on every undelegated `slurp` of a path inside the container and on every delegated fact derivation — around twenty-five sites with nothing useful to say — and the implementer's only recoveries would be to bless them wholesale, which turns the check into noise, or to invent an unstated discriminator, which is how the first version of this design went wrong.
