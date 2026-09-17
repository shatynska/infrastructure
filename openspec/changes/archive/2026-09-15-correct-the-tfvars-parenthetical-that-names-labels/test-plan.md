## Test derivation for `correct-the-tfvars-parenthetical-that-names-labels`

This is not an OpenSpec artifact and is not read by `openspec instructions apply` — read it on purpose before implementing.

### Independent verification performed

The delta spec (`specs/iac-repo-foundations/spec.md`) carries one `MODIFIED` requirement, *Version Control Excludes State and Secrets*. I compared it byte-for-byte against the currently recorded requirement at `openspec/specs/iac-repo-foundations/spec.md` (lines 50-72) rather than taking `design.md`'s claim on trust. Result: the only difference anywhere in the requirement is the dropped word `labels,` inside one table cell's parenthetical (line 10 of the delta vs. line 57 of the current spec). All three `#### Scenario:` blocks are byte-identical between delta and current spec — no scenario text changed at all.

I also grepped the full test-path glob (`.github/tests/*.py`) for anything that reads this requirement's table cell or its illustrative parenthetical (`"Version Control Excludes State and Secrets"`, `"Non-secret stack configuration"`, `"server type, region, image"`, and `labels`). One test cites the requirement by name — `test_every_stack_carries_its_committed_non_secret_configuration` in `.github/tests/test_terraform_stacks_are_the_iterated_unit.py:836-855` — but it asserts only that each stack directory carries a `terraform.tfvars` file; it does not read or assert the parenthetical's word list, so it is unaffected by this correction. No test anywhere in the glob reads the parenthetical.

I ran the full suite as the baseline: `python3 -m unittest discover --start-directory .github/tests` from the repository root — **1276 tests, OK** (full run, no scoping).

### Scenario accounting (3 of 3 accounted for)

| Scenario | Status | Reason |
|---|---|---|
| "Local state is never staged" | Uncovered by this pass | Byte-identical to the current spec's scenario of the same name; this `MODIFIED` delta changes nothing in or bearing on this scenario — the changed text (the parenthetical) sits outside every scenario block and outside this scenario's WHEN/THEN entirely. No new behavior is introduced for it, so nothing is derived here under the ADDED-equivalent treatment for revised scenarios. |
| "CI has the environment configuration it needs" | Uncovered by this pass | Same: byte-identical scenario text; the scenario's own THEN ("non-secret `terraform.tfvars` values SHALL be present") does not name or depend on the parenthetical's word list, which is illustrative rather than normative. Already-existing coverage, if any, is untouched by this pass — see `test_every_stack_carries_its_committed_non_secret_configuration` above, itself unaffected. |
| "Secret-bearing variable file is not committable" | Uncovered by this pass | Same: byte-identical scenario text, no bearing on the corrected parenthetical. |

No scenario reached this pass through a `REMOVED` or `RENAMED` delta; this is the requirement's only delta operation.

### Assertion classification

Not applicable — no new test was written by this pass, so there is no assertion to classify under `testing`'s specified/derived/deliberately-untested rule.

### Obsolete-tests list

**Not applicable.** This change carries one `MODIFIED` delta, so the obsolete-test search was performed rather than skipped: I searched `.github/tests/*.py` (the dispatched glob) for any test bearing on the superseded text (the word `labels` inside this table cell). One test names the requirement (`test_every_stack_carries_its_committed_non_secret_configuration`, cited above) but asserts file presence only, not the parenthetical's contents, so it is not superseded — it is evidence for "none found," not a candidate entry. No test anywhere in the glob reads or asserts the parenthetical's word list. Result: no bearing test exists in the searched scope; the list is empty because none was found by this search, not assumed empty by default.

### Unresolved project questions

None. The dispatched convention file (this project's `AGENTS.md`, read in full) directly names the test command and glob for this class of subject (the "Testing" section's table, "static read of a committed file" row), so no runner or stack-skill ambiguity arose. No stack-specific skill applies to this subject (a Markdown spec correction with no `.tf`, `.yml`, or Ansible content); this is recorded here as the "record the absence" step rather than left silent.

### Baseline

Full baseline taken: `python3 -m unittest discover --start-directory .github/tests`, run from the repository root — 1276 tests, OK, no scoping applied.

### Conclusion

No test is owed by this change. Independently confirmed (not merely deferred to `design.md`'s argument): every scenario in the `MODIFIED` delta is byte-identical to the currently recorded spec, and no test in the dispatched glob reads the corrected parenthetical. This pass wrote no test, edited no test, and wrote nothing outside this manifest.
