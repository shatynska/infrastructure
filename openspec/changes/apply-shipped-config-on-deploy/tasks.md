Two steps this change owes are not in this list, because they happen after the
commit that writes this file and so could never be ticked in it: removing the
branch and removing the working tree, both after the record's own pull request
has merged and every other pull request this change opened is merged. The
archive step itself is task 5.5 below and is unaffected.

## 1. Make the configuration visible to Compose

- [x] 1.1 Add a `labels:` entry to `prometheus`, `alertmanager` and `grafana` in `platform/docker-compose.yml`, each holding the digest this change's `design.md` Decision 3 specifies exactly: SHA-256, hex, first 12 characters, over the concatenation of `<config name>\n<content>\n` for each config that service mounts, in mount order, and over that service's configs alone. Verify by task 4.4's comparison — this branch's file against its parent commit's, in one environment — that exactly those three hashes moved and no others. Not against the running containers: see 4.4 for why that comparison is confounded.
- [x] 1.2 Comment the labels in the style the surrounding file uses: what the digest covers, why it exists — Compose's config-hash does not include inline `configs:` content, and that content is copied into the container at creation rather than bind-mounted, so without this a configuration-only deploy recreates nothing, changes nothing and reports success — and that the static check names the correct value on a mismatch. Verify by reading the diff: a reader who does not know the defect should not have to leave the file.

## 2. Derived tests

Written by an author other than whoever implements section 1, from the added
requirement in this change's delta spec rather than from the labels as written.
Two things are fixed here rather than left open, and the author should know
which: the digest algorithm, because it is not discoverable from the requirement
and two authors must reach the same value (`design.md` Decision 3), and the
properties themselves, named per task below. What remains the author's is how
each assertion is expressed, where in the suite it belongs, what each failure
message says — Decision 2 rests the whole friction budget on that message naming
the correct value — and actually performing the falsification check each task
names, which is where a tautological assertion gets caught.

What the derive-from-the-spec rule protects is preserved regardless: nothing
below sends the author to the committed label values, so the tests cannot be
derived from the implementation. Note too that these assertions are not a
one-time check of this implementation's arithmetic — they are the standing
guarantee Decision 2 depends on, run against every future edit to an embedded
config.

Test command: `python3 -m unittest discover --start-directory .github/tests`,
run from the repository root; test-path glob `.github/tests/*.py`. The Terraform
and Molecule rows of `AGENTS.md`'s testing table do not apply — this change
touches neither a Terraform module nor an Ansible role.

- [x] 2.1 Assert that every service declaring `configs:` carries the checksum label, discovering those services from the file rather than from a list of names, per this change's `design.md` Risks — the check must not hold only until someone adds a service. Verify the assertion fails against a copy in which a fourth service gains a `configs:` entry and no label.
- [x] 2.2 Assert each label's value equals a recomputation of the digest from the content of the configs that service mounts, and that the failure message names the value the label should hold. Derives from the requirement's third scenario. Verify the assertion fails against a copy with one alert rule edited and the label left alone.
- [x] 2.3 Assert the digest covers all of a service's configs rather than only the first, so a change in the second or later one cannot go unnoticed. Verify against a copy in which only `grafana`'s last dashboard is edited.
- [x] 2.4 Assert the three labels are pairwise distinct, and that editing one service's config moves only that service's *expected* value. Derives from the requirement's second scenario. Be clear about what this does and does not add: task 2.2 is what excludes every wrong construction, because the labels are literals that either equal the specified per-service recomputation or do not — including the awkward variant that digests a service's own configs together with all of them, which is distinct per service yet moves all three on any edit. This task contributes distinctness, a true but weak necessary condition, and a regression guard on the recomputation function itself. Its second clause is a property of that function rather than of the committed labels, since a literal cannot respond to a mutated copy — so write it as a guard, not as though it constrained the implementation. Verify against a copy where one config is edited and the other two services' expected values are recomputed.
- [x] 2.5 Assert no service without `configs:` carries the label, so a copy-paste cannot quietly widen what gets recreated. Verify against a copy that adds the label to `postgres`.
- [x] 2.6 Assert the digest's framing distinguishes content moved between two configs of the same service — the config name participates, per `design.md` Decision 3, so a bare concatenation cannot be what is hashed. Verify against a copy in which a block moves from `prometheus_config` into `prometheus_rules` with the total content unchanged.
- [x] 2.7 Run the whole suite and confirm it is green apart from the assertions section 1 has not yet satisfied.
- [x] 2.8 Commit the derived tests exactly as their author wrote them, before any folding or relocation, per `docs/change-queue.md` entry 42. Verify the commit contains tests only.

## 3. Bookkeeping

- [x] 3.1 Add a `docs/change-queue.md` entry for the wider backstop this change deliberately does not build: after `up -d --wait`, compare each running container's `com.docker.compose.config-hash` against `docker compose config --hash='*'` and fail the deploy on a mismatch. Verify the entry records that it does not subsume this change — without a label the two hashes agree while the configuration sits unapplied — and that it touches the generic `app-deploy` script, so it affects every application.
- [x] 3.2 Record in `platform/README.md` that editing an inline config requires regenerating that service's checksum label, that the static check names the correct value, and that the edit will recreate that service on the next deploy. Verify a reader editing an alert rule would find this before opening a pull request.

## 4. Verification

- [x] 4.1 Run `python3 -m unittest discover --start-directory .github/tests` from the repository root and confirm every assertion from section 2 passes.
- [x] 4.2 Run `pre-commit run --all-files` and confirm it is clean. Provision first — a fresh working tree has no Galaxy roles, and the Ansible syntax check fails without them in a way that looks like a defect in this change.
- [x] 4.3 Run `openspec validate --strict apply-shipped-config-on-deploy` and confirm it passes.
- [x] 4.4 Confirm the labels move exactly the three services' hashes and no others, by computing `docker compose config --hash='*'` over this branch's file and over its parent commit's, in the same environment, and diffing. This is the pre-merge half of the confirmation and can only be taken before the deploy.

  It is deliberately a before/after comparison of the file against itself rather than against the running containers, because the latter is **not performable**: five of the eight services interpolate `${...}` from `.env`, which is not in the repository, so a local run computes them with empty values and their hashes differ from the host's for that reason alone. `prometheus` and `alertmanager` happen to be comparable — neither interpolates anything into its service block, and both matched the host exactly before this change — but `grafana` does interpolate, so the one comparison that would cover all three services is confounded. Computing on the host with the real `.env` would need read access to `/opt/platform`, which the operator account does not have.
- [x] 4.5 Dispatch the change's code review over the diff and record the verdict; fix and re-review until it clears.

## 5. Ship

- [ ] 5.1 Open the pull request once section 4 is green, and wait for the operator's confirmation that continuous integration passed, that it merged, and that the platform deploy is healthy.
- [ ] 5.2 Read the deploy log and confirm it reports `Recreated` for `prometheus`, `alertmanager` and `grafana`, and `Running` for the rest. A deploy reporting `Running` for all nine is this change having failed. It is evidence that the stack definition is not reaching the host — the assumption `design.md`'s Risks records as unestablished — but that is not the only explanation: a label whose value fails to move the hash as the host's Compose computes it would produce the same log. Read the containers' labels to tell the two apart: a container carrying the new label was delivered and not replaced; one without it was never delivered. Report the outcome rather than proceeding, whichever it is.
- [ ] 5.3 Confirm the effect by the three steps in this change's `design.md` under "Confirming the effect". The decisive one is that Prometheus now serves the two rules `alert-on-certificate-expiry` shipped and Alertmanager carries its route — configuration already committed and already shipped, which only a deploy that applies shipped configuration can bring into effect. Wait for the operator's confirmation.
- [ ] 5.4 Bring the branch back to the freshly fetched trunk.
- [ ] 5.5 Commit the specification record and open its own pull request.
