## 1. Settle the namespace and its entry point

- [x] 1.1 Choose the sanitised-basename-plus-digest form for the namespace value (design Decision 3) and verify that computing it twice in one working tree yields the same string, and that it differs between two working trees whose basenames match
- [x] 1.2 Bound the resolved name (design Decision 3a): verify that a scenario carrying a namespace of the length this repository's own change names produce creates successfully with a short explicit `hostname` declared, and verify by removing that `hostname` that the run fails with `hostname is too long (maximum 64 bytes)` — so the bound is known to be doing work rather than assumed
- [x] 1.3 Choose the sentinel's exact text (design Decision 4) and verify by running `molecule create` with the variable unset that it fails with `Invalid container name` and that the sentinel's instruction is legible in the error
- [x] 1.4 Write the entry point that computes the namespace, exports it together with `ANSIBLE_HOME` and `ANSIBLE_COLLECTIONS_PATH`, and execs Molecule; verify it runs one scenario green from a working tree whose namespace is unset in the ambient environment
- [x] 1.5 Verify the entry point fails loudly, naming the one-time `ansible-galaxy` install, when the shared collections path is absent — rather than letting Molecule fail with the same `community.docker.docker_login` error that means something else (design Decision 2)
- [x] 1.6 Verify the entry point fails rather than exporting an empty namespace if the working tree cannot be resolved

## 2. Namespace every authored scenario

- [x] 2.1 For each authored scenario, search its directory for any other reference to its current instance name — an inventory group, a `host_vars` key, a `hostvars[...]` lookup in `verify.yml` or `side_effect.yml` — and record what is found before renaming anything, so the rename is not discovered to be incomplete at run time
- [x] 2.1a Search each role's own `tasks/`, `templates/`, `defaults/` and `handlers/` for `ansible_hostname`, `ansible_nodename` and `inventory_hostname`, and record what is found: declaring an explicit `hostname` changes what the first two resolve to inside every container, from the instance literal to the new short name, and that reaches beyond the scenario directory 2.1 sweeps
- [x] 2.2 Add the namespace and its refusing default to `platforms[].name`, and a short explicit `hostname`, in all authored `ansible/roles/*/molecule/*/molecule.yml`, leaving each existing name as the prefix; verify every file still parses as YAML, that no two names collide within one working tree, and that every reference found in 2.1 was updated with it
- [x] 2.3 Verify the Galaxy-installed `geerlingguy.docker` scenario is untouched, and that it is excluded by the manifest-derived rule rather than by name
- [x] 2.4 Run one role's full scenario set through the entry point and verify from `docker ps` during the run that the container carries the working tree's namespace — not only that the run went green (design, Risks: this change's own verification is subject to the hazard it fixes)
- [ ] 2.5 Verify a second, concurrently-run working tree drives a differently-named container, which is the behaviour the change exists to produce
- [x] 2.6 Run the full suite through the entry point and verify from the SCENARIO RECAP that every scenario every role declares was executed, rather than reading the exit code alone

## 3. Relocate the ephemeral directory

- [x] 3.1 Verify through the entry point that a run's ephemeral directory resolves under the working tree's `ANSIBLE_HOME`, retaining the `molecule.<id>.<scenario>` split, and that `~/.ansible/tmp/` is not written to during that run
- [x] 3.2 Verify `molecule test --all` completes for a multi-scenario role under the relocated home, confirming the split survives the invocation `.github/tests` requires

## 4. Assert it statically

- [x] 4.1 Add assertions over every authored scenario's instance name — the namespace present, and the default one that cannot name a container at all rather than one that merely looks wrong — reusing `authored_scenario_files()` so a scenario added later is covered without an edit; verify each fails against a fixture scenario carrying a bare literal name, and separately against one carrying a benign default such as `-unset`, which is the alternative design Decision 4 rejects
- [x] 4.2 Add an assertion that every authored scenario declares a `hostname`, since a scenario added later without one inherits the 64-byte limit through its name; verify it fails against a fixture scenario declaring none
- [x] 4.3 Add the assertion that `AGENTS.md` states the binding, matched on its own load-bearing words; verify it fails on a copy of the tree with that section removed
- [x] 4.4 Verify every new assertion fails on the pre-change arrangement before the fix is applied — against a copy, never by mutating the working tree — and that each one *fails* rather than erroring, an error establishing nothing about the property
- [x] 4.5 Run `python3 -m unittest discover --start-directory .github/tests` from the repository root and verify it passes; verify it also passes against a tree carrying no installed Galaxy content, so the manifest-derived exclusion behaves as it does on a runner rather than as it does on a provisioned workstation

## 5. Bind the rule in AGENTS.md

- [x] 5.1 Write the binding section adjacent to the shared-service rule, naming Molecule, the two live handles, the namespace, the entry point, and the one-time collections install a fresh machine needs; verify `.github/tests` 4.3 passes against it
- [x] 5.2 State in that section how a session brings its namespace to the project's initial state — `AGENTS.md`'s shared-service rule requires that half too, and it is unbound without it; verify the section names both the container and the ephemeral directory
- [x] 5.3 Revise the Testing section's shared-state paragraphs so they describe the hazard as bounded by this mechanism rather than as standing, and verify the existing `TestTheConventionsFileStatesTheMoleculeSharedStateHazard` assertions still pass or are updated deliberately rather than incidentally
- [x] 5.4 Verify no other statement in `AGENTS.md` still tells a session that coordination between sessions is the whole safeguard

## 6. Carry the pipeline with it

- [x] 6.1 Supply the namespace in `ansible-verify.yml` so continuous integration satisfies the sentinel like any other caller, and verify the Molecule matrix runs green on a pull request that touches `ansible/` — this change cannot land on a skipped matrix
- [x] 6.2 Verify the aggregating job still concludes on the matrix's behalf, and that no job gained a write scope or an `environment:`

## 7. Record what this change moves

- [x] 7.1 Record in `docs/deferred-work.md` the residues this design accepts rather than solves — the shared ephemeral write on a namespace-less run, that namespaces accumulate unreclaimed, that a working tree renamed after a run orphans its state, and the rejected stronger form that would make the entry point unavoidable — since `design.md` is archived with the change and would take them with it
- [x] 7.2 Delete change-queue entry 8, and correct entry 11's account where it assumes the shared-state hazard is still open; verify no remaining entry or source comment cites entry 8 after its deletion
- [x] 7.3 Record a change-queue entry (46, renumbered from 43 when the trunk claimed that number mid-change) for adopting a ShellCheck pre-commit hook, this change having added the repository's first script with no linter to check it; verify the entry states why it was not folded in here
- [ ] 7.4 Verify the full suite and `openspec validate --all` pass, then archive the record through its own pull request

## Not performed

- 2.5, the concurrent half only. Two working trees were verified to derive different namespaces and to drive differently-named containers — `namespace-the-molecule-suite-per-working-58721e` here against `infrastructure-e8a5b4` from the main working tree — but the two runs were not performed *simultaneously*.
  Reason: another session held a locked working tree on this machine throughout, and the only way to exercise simultaneity against it is to run the collision this change exists to prevent. A run started from a second tree of this branch was set up and abandoned for the same reason: it proves nothing the derivation does not already establish, since the container name and `ANSIBLE_HOME` are both functions of the working tree's path and were each observed to differ. The property is verified by construction and by observation, not by concurrency; the pull request's own CI matrix exercises the entry point on an isolated runner in addition.


- Verifying the entry point with ShellCheck.
  Reason: this repository carries no ShellCheck hook in `.pre-commit-config.yaml` and none of its three test commands would run it, so the check would be an unpinned, unrepeatable tool invocation — the shape `AGENTS.md` warns about, where verification that cannot reach what it needs is indistinguishable from a pass. Adopting ShellCheck is worth doing and is a change of its own; it is recorded in `docs/change-queue.md` rather than folded in here.
