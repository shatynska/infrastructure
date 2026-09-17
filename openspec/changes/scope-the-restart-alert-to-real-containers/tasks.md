## 1. Derive the tests from the approved plan

- [ ] 1.1 An author other than the implementer writes the static assertions for the delta's scenarios into a new `.github/tests/` module, from the delta spec rather than from the rule, and records the scenario-to-test mapping plus anything deliberately left uncovered in this change's `test-plan.md`. Verify by running `python3 -m unittest discover --start-directory .github/tests` from the repository root and confirming the new assertions fail against the unmodified rule — a baseline recorded before any implementation exists, so that passing later means something.

## 2. Narrow the rule

- [ ] 2.1 In `platform/docker-compose.yml`, add the `{name!=""}` selector to both metric selectors in `ContainerRestartingOrOOMKilled`'s expression — `container_oom_events_total` and `container_start_time_seconds` — leaving the thresholds, the `for:`, the labels and the annotations untouched. Verify with `git diff platform/docker-compose.yml` showing exactly those two selectors changed and nothing else.
- [ ] 2.2 Verify the file still renders and parses as Compose, the way `pr-validation.yml` does it: `cp platform/.env.example platform/.env && docker compose -f platform/docker-compose.yml config >/dev/null && rm platform/.env`, run from the repository root and expected to exit 0.
- [ ] 2.3 Verify the `prometheus_rules` entry is still valid Prometheus rule YAML by parsing it the way the new test module does — load the Compose file, undo the `$$` escaping in the entry's `content`, parse it as YAML, and confirm the narrowed rule is among the groups with both selectors present.

## 3. Verify

- [ ] 3.1 Run `python3 -m unittest discover --start-directory .github/tests` from the repository root and confirm the whole suite is green — the new module included, which turns the recorded baseline from failing to passing, and every existing module, which establishes the change broke none of them.
- [ ] 3.2 Run `pre-commit run --all-files` and confirm it passes, having first provisioned this working tree per README's Local setup step 5 (`ansible-galaxy role install -r ansible/requirements.yml -p ansible/roles`), so that an unprovisioned tree's `ansible-playbook --syntax-check` failure is not mistaken for a defect in this change.
- [ ] 3.3 Commit the implementation, then dispatch `ai-toolkit:change-code-reviewer` over the committed diff and address what it reports.

## 4. Ship

- [ ] 4.1 Open the pull request and verify continuous integration passes on the branch head — `PR Validation` in particular, which runs the static suite unconditionally.
- [ ] 4.2 Wait for the operator's confirmation that the pull request merged and that `Platform Deploy` reported healthy for both stacks. Do not infer any of that from a green pull request.

## 5. Confirm the effect on the deployed staging host

- [ ] 5.1 Confirm the deployed rule is the narrowed one: on staging, read it back out of the running Prometheus with `docker exec platform-grafana-1 wget -qO- "http://prometheus:9090/api/v1/rules"` and confirm `ContainerRestartingOrOOMKilled`'s expression carries `name!=""` on both metrics. A rule file that did not reload is what this catches.
- [ ] 5.2 Confirm the narrowed expression selects only containers: evaluate its two halves against staging's Prometheus and confirm every series returned carries a `name`, and that the count matches `docker ps -q | wc -l` on that host. Measured before this change on 2026-09-17: 46 `container_start_time_seconds` series of which 10 had a name, and 55 `container_oom_events_total` series of which 10 had a name.
- [ ] 5.3 Confirm the negative scenario against the churn that actually provoked the incident: open and close more than three short-lived SSH sessions to the staging host inside ten minutes, which recreates the `/user.slice/user-1000.slice/…` control groups. **Establish that the churn happened before reading the silence**, because "no alert fired" is evidence only if the condition recurred: confirm `changes(container_start_time_seconds{name=""}[10m]) > 3` returns that session control group at that moment, and only then confirm no `ContainerRestartingOrOOMKilled` appears in Prometheus's alerts and none reaches the Slack channel. The sessions must be **sequential** — each closed before the next opens, since an overlapping session keeps `user-1000.slice` alive and the cgroup is never recreated — and spaced past a scrape interval, for the reason 5.4 gives. Four quick overlapping `ssh` invocations produce a clean channel that means nothing and is indistinguishable from a confirmed fix. Before this change that sequence fired the alert; a clean channel afterwards, with the churn shown to have occurred, is the observable effect the operator is asked to confirm.
- [ ] 5.4 Confirm the positive scenario still works: restart one container more than three times in ten minutes, spacing the restarts at least 35 seconds apart so each start is scraped — `fix-cadvisor-containerd-snapshotter` recorded that a faster sequence undercounts `changes()` and proves nothing — and confirm the alert fires naming that container. Use a throwaway container, not a platform service.
- [ ] 5.5 Report to the operator what 5.1 through 5.4 showed and wait for their confirmation before archiving.

## 6. Archive

- [ ] 6.1 Bring the branch back to the freshly fetched trunk, run `openspec archive scope-the-restart-alert-to-real-containers`, stage the result with `git add -A` — the archive moves files without telling git, and the repository's sweep tests fail until it is staged — and open the record's own pull request.

Removing the branch and this working tree happens after that pull request merges, which is after the commit that writes this file, so it is not a task here. `AGENTS.md` records it as prose for exactly that reason.
