Verification for a docs-only change is the static suite from the repository
root and `pre-commit run --all-files`. Neither reads prose for truth, so each
task below states the evidence its sentence rests on — and the four findings do
not all rest on the same kind:

- **Sections 2 and 3 are behavioural** and cite `configure-the-staging-host`'s
  converge, recorded under `## Verification record` in that change's archived
  task list (10.2 and 10.1 respectively). Check the citations there; do not take
  them from here.
- **Sections 1 and 4 are documentary** and cite nothing but the committed files:
  §4.1 has a `source` fallback and §6.0 has none, and §6.1 offers no way to
  check the token it tells you to create. Both are verifiable by reading, need
  no run, and would be just as true had the converge gone perfectly. A machine
  without direnv and a truncated-paste `401` are what made them noticeable, not
  what makes them true.

## 1. §6.0 — the `source` fallback, and why it is safe here

- [x] 1.1 Add the non-direnv path to §6.0, matching §4.1's shape: `source .envrc` from `ansible/`, once per shell. Do the same in `ansible/.envrc.example`'s header, whose copy instructions likewise stop at `direnv allow` (line 4) — it is the file the operator has open at that exact step, so fixing §6.0 alone leaves the instruction they are actually looking at unchanged. Verify by reading §4.1 and confirming the three now offer the same alternative rather than one assuming a tool the others do not.
- [x] 1.2 State the asymmetry at §6.0, where the fallback is offered: sourcing **Terraform's** `.envrc` is the hazard §4.1 describes, because the root and staging files both export `HCLOUD_TOKEN` with different values and the export outlives the directory. Sourcing **`ansible/.envrc`** carries no such risk — `HCLOUD_TOKEN_PROD` and `HCLOUD_TOKEN_STAGING` collide with nothing and mean the same thing anywhere. §4.1 already says this, in the paragraph explaining the hazard; cross-reference it rather than restating it in full, and make §6.0 say enough that a reader who starts at stage 6 is not left to infer it. Verify the sentence names both variables and does not merely say "it is safe".
- [x] 1.3 Fix `README.md`'s local-setup step 4, which says "`direnv allow` is not optional". True of direnv users, false as a statement about the procedure. Rephrase so it is the *allow step* that is not optional **when using direnv**, and point at the `source` alternative. Verify by reading the step end to end as someone without direnv installed.

## 2. §6.3 — what a failed converge looks like, and how to recover

- [x] 2.1 Add a subsection to §6.3 for a converge that fails partway. It SHALL say that the failure leaves a **partially-converged host** — the roles ahead of the failing one have applied — and that the recovery is to correct the input and re-run the same command, every role being idempotent, rather than to rebuild the host or start over. Evidence: `configure-the-staging-host` 10.2, where a failure at `tailscale up` left `docker` and `hardening` applied and the re-run completed at `ok=76 changed=28 failed=0`.
- [x] 2.2 In that subsection, name the `no_log` masking specifically. A failure in *Bring the host onto the tailnet* reports `"censored": "the output has been hidden due to the fact that 'no_log: true' was specified for this result"` and nothing else, because the auth key would otherwise be printed. Give the recovery that actually works: SSH to the host as root and run `tailscale up --authkey=…` by hand, which prints what was masked; `tailscale status` and `journalctl -u tailscaled` for context. Verify the commands match what the role runs — `ansible/roles/tailscale/tasks/main.yml`'s task is `tailscale up --authkey={{ tailscale_auth_key }}`.
- [x] 2.3 Say that the masking is deliberate rather than a defect, and attribute it correctly: it is the **role's own decision**, stated in the comment above the task in `ansible/roles/tailscale/tasks/main.yml` — "`no_log` because the auth key would otherwise appear in the task's command output". Do **not** cite *Tailscale auth key is never committed* as obliging it: that requirement is about the key staying out of version control, and a grep of `openspec/specs/` for `no_log`, `masked` and `censored` returns nothing. Writing a false citation into the operator's document is the exact defect this change exists to remove. A reader who thinks the masking is a bug will look for a way to turn it off; one who knows why it is there will go to the host instead.

## 3. §6.3 — `--check --diff` and its two permanent false positives

- [x] 3.1 Qualify the sentence "`--check --diff` is useful on every run after the first". Add that **two `tailscale` tasks report `changed` on every check-mode run and always will** — *Add the Tailscale apt signing key* and *Add the Tailscale apt repository*, both `ansible.builtin.get_url` with no `checksum:`, which cannot confirm a file already matches without downloading it, and check mode will not. So a healthy host reads `changed=2`, and the baseline to compare against is two rather than zero. Evidence: `configure-the-staging-host` 10.1 against production, plus a fixture reproduction recorded there.
- [x] 3.1a Write the reciprocal half into `docs/change-queue.md` entry 23, beside its existing false-positives paragraph: that §6.3 now tells operators a healthy host reads `changed=2` and names both tasks, so whichever remedy entry 23 takes, §6.3 changes with it — otherwise the document trains operators to discount the very signal that change exists to create. **This change owes that line, not entry 23**: before this merges, no document states that baseline, so entry 23's implementer cannot be expected to discover a dependency nobody recorded. Same shape as `configure-the-staging-host` task 8.5, which added the reciprocal of an ordering line "so the coupling is readable from either end rather than only from the newer entry".
- [x] 3.2 Point the reader at `docs/change-queue.md` entry 23, which carries the same finding for the change that would turn `--check --diff` into the host layer's drift detector. Cite it as a queue entry, not by a path under `openspec/changes/`. Verify the citation form against `AGENTS.md`'s "Citing this repository's own specifications and change records" and by `python3 -m unittest discover --start-directory .github/tests` passing, which enforces it.

## 4. §6.1 — checking the GHCR token before relying on it

- [x] 4.1 Add a check after the token-creation paragraph: a request to `https://api.github.com/user` with the token as the password in basic auth returns **`200`** and an `x-oauth-scopes` header naming `read:packages`. Three things the wording must get right, and each was got wrong first:

      - **Do not put the token in the command line.** `curl -u <user>` with no password prompts for it, which keeps it out of both shell history and `ps`. §6.1's neighbouring decrypt check is careful in exactly this way — it "prints the value's length, never the value" — and this check should match that standard rather than undercut it.
      - **Assert `200`, not `HTTP/2 200`.** The protocol prefix depends on the client and the negotiation, not on the token.
      - **Name the fine-grained-token case.** A fine-grained PAT returns `200` with *no* `x-oauth-scopes` header at all, which reads as "no scopes" and is really "wrong token type" — this procedure wants a **classic** token. Without that caveat the check produces a confident misdiagnosis.

      Say what each outcome means: `401` is expired, revoked or truncated; a `200` whose scopes omit `read:packages` authenticates but cannot pull, and would fail later at `docker compose pull` rather than now.
- [x] 4.2 Note that the token's absence is tolerated, so this check is not a gate: `deploy_user` guards the registry login with a `when:` and skips it, per *Host Authenticates to GHCR for Application Image Pulls*. A reader stuck on the token should know they can proceed without it and return to it. Verify against `ansible/roles/deploy_user/tasks/main.yml`, whose login task carries that condition.

## 5. Verification

- [x] 5.1 `python3 -m unittest discover --start-directory .github/tests` from the repository root, passing — the suite that enforces the citation form and the repository-wide conventions this change's prose is subject to.
- [x] 5.2 `pre-commit run --all-files`, passing. Note what this does **not** establish: no hook reads prose for truth, so the accuracy of every sentence added here rests on the observations cited per task, not on a green check.
- [x] 5.3 Read §6 end to end as an operator who has never run it, and confirm that every command in it is one that has actually been executed — during `configure-the-staging-host`'s converge, or in task 6.2 below — or is marked as not yet exercised. That change's task 7.2 set this obligation for the stage; this change is subject to it too, and 6.2 is where the commands this change *adds* get executed rather than merely asserted.

## Verification record

**5.1** `python3 -m unittest discover --start-directory .github/tests` — 557,
OK. **5.2** `pre-commit run --all-files` — all hooks pass. Neither establishes
that a sentence is true; what follows is what does.

**5.3 — stage 6 read end to end.** Every command in the stage has now been
executed at least once, in `configure-the-staging-host`'s converge or in this
session, with these exceptions, named because this change holds itself to that
standard explicitly:

- `direnv allow`, exercised by anyone who has direnv, and whose absence is the
  case section 1 exists to handle;
- `read -rs KEY`, `tailscale up --authkey="$KEY"` and `tailscale status --json`,
  which are round-2 rewordings of commands that *were* run — 10.2 ran
  `tailscale up` with the key inline, 10.4 ran plain `tailscale status` — but
  not in the form the document now prints. They sit inside the one section 6.2
  waives as unobservable without deliberately breaking a converge.

**Corrections made after code review, each a claim that was not true as first
written.** Recorded rather than quietly fixed, because in a change whose subject
is documentary accuracy the corrections are the substance:

- §6.3a said "the failing one and everything after it has not [applied]".
  False, and self-contradicted thirteen lines later by the instruction to expect
  `tailscaled` active: *Bring the host onto the tailnet* is the **last** task in
  `ansible/roles/tailscale/tasks/main.yml`, so the keyrings directory, both
  `get_url` tasks, the pinned package and the enabled unit have all applied.
- §6.3a told the operator to wait for `tailscale status` to report `Running`.
  It never does. `Running` is `BackendState` in `tailscale status --json`, which
  is the field the role's own `when:` reads. §6.4 carried the same error from an
  earlier change and is corrected with it.
- §6.3a put the auth key on a command line, contradicting the standard §6.1
  sets ninety lines earlier for the GHCR token. Now `read -rs`.
- §6.3's "compare against two" was true and incomplete: two is the baseline for
  what check mode can *see*. Seven `command` tasks skip and five
  `geerlingguy.docker` tasks swallow failures, which entry 23 already records
  and §6.3 did not.
- §6.1's `grep -i '^HTTP\|x-oauth-scopes'` uses a GNU BRE extension that prints
  nothing on the macOS workstations §0.2 supports — indistinguishable from the
  fine-grained-token diagnosis it would be read as. Now `grep -iE`, and `curl
  -sS` so a transport failure says so rather than looking like the same thing.
- §6.1 claimed a fine-grained token "cannot pull packages". Plausible, and
  evidenced by nothing in this repository; the confirmation gate cannot produce
  it either, since the operator's token is classic. Softened to what is
  checkable.
- The end-state summary at the top of the document still promised "a staging
  server that is provisioned and not configured". `configure-the-staging-host`
  updated the section that says otherwise and missed the summary above it.

**6.2 — the confirmation observations.** Two are already satisfied from this
session: `ansible/.envrc` sourced with no direnv hook, after which
`ansible-inventory -i inventory/staging.hcloud.yml --graph` resolved
`staging-server`; and the token check returning `200`. The third — a check-mode
run against **staging** reporting `changed=2` on the two named tasks — is
outstanding, and matters because 10.1 established that figure on production
only, where it could still have been a coincidence of one host.

## 6. Ship

- [x] 6.1 Open the pull request once verification passes and the code review has cleared, and wait for the operator's confirmation that it merged. Nothing here deploys.
- [x] 6.2 **The confirmation gate is answered, not waived.** Three of the four additions are observable today, against the staging host that already exists and with credentials the operator already holds. Run them and record the output:

      - **§6.0's fallback.** In a shell with no direnv hook: `cd ansible && source .envrc && ansible-inventory -i inventory/staging.hcloud.yml --graph` resolves `staging-server`. That is the whole claim of section 1 — that the procedure works without direnv.
      - **§6.3's check-mode baseline.** `ansible-playbook playbooks/host-baseline.yml -i inventory/staging.hcloud.yml -e target_environment=staging --vault-id staging@prompt --private-key ~/.ssh/<company>-root --check --diff` against the converged staging host reports `changed=2`, and the two are the tasks §6.3 now names. Section 3 says a healthy host reads two; this is that sentence being true of a host known to be healthy, on a second environment, which the production run did not establish.
      - **§6.1's token check.** The command as written returns `200` and an `x-oauth-scopes` header naming `read:packages`.

      **One addition cannot be observed and is the only thing waived**: section 2's failed-converge recovery, which would require deliberately breaking a converge to demonstrate. It is already evidenced by `configure-the-staging-host` 10.2, where the failure happened for real. Name that one as the waived part, in the first waivable class, and let the operator waive it — waiving one's own gate is not the confirmation this step exists to obtain.

      An earlier draft of this task claimed the waiver for the whole change on the grounds that the next stage-6 execution is an unscheduled company bootstrap. That is true of the *stage* and false of these three additions, and task 5.3 already commits to running the commands anyway. Recorded because a change that improves a document is exactly the kind most able to dodge a confirmation gate, and it nearly did.
- [x] 6.3 Bring the branch back to the freshly fetched trunk and archive the record with `openspec archive`. Verify `openspec validate --archived` passes.

## Ship record

**6.1** Pull request #132, merged as `93fd6e4` on 2026-09-11. Nothing here
deploys, and none is claimed: a docs-only change matches no path filter in the
Terraform workflows.

**6.2 — three observations made, one part waived.** The gate is answered.

- **§6.0's fallback.** Satisfied in the authoring session: `ansible/.envrc`
  sourced in a shell with no direnv hook, after which `ansible-inventory -i
  inventory/staging.hcloud.yml --graph` resolved `staging-server`. Re-confirmed
  in this session, in a freshly provisioned working tree, with the same result.
- **§6.1's token check.** Satisfied in the authoring session: `200` with an
  `x-oauth-scopes` header naming `read:packages`.
- **§6.3's check-mode baseline, which was the outstanding one.** Run on
  2026-09-11 against the converged staging host:

      ansible-playbook playbooks/host-baseline.yml \
        -i inventory/staging.hcloud.yml -e target_environment=staging \
        --vault-id staging@<file> --private-key ~/.ssh/<company>-root \
        --check --diff

  `PLAY RECAP` — `staging-server : ok=74 changed=2 unreachable=0 failed=0
  skipped=22`, and `localhost : ok=2 changed=0`, the guard play. The two
  changed tasks are *Add the Tailscale apt signing key* and *Add the Tailscale
  apt repository* — the two §6.3 names and no others, extracted from the run's
  own output rather than assumed from the count. This is what the task wanted
  and `configure-the-staging-host` 10.1 could not give: the figure holding on a
  second host, so two is the role's property rather than a coincidence of
  production.

  The run used a password file rather than `staging@prompt` because this
  session cannot answer an interactive prompt. The file was written by the
  operator outside the repository, read once, and shredded; the password
  appears in no transcript, no history and no committed file. The document is
  unchanged and still prints `@prompt`, which is the right instruction for a
  human at a terminal.

**The waived part, named as the task requires.** §6.3a's failed-converge
recovery cannot be observed without deliberately breaking a converge, which is
the first waivable class — *no observation can actually be made*. **The
operator waived it on 2026-09-11**, on the grounds the task itself records:
that path is already evidenced by a failure that happened for real, in
`configure-the-staging-host`'s task 10.2, where a failure at `tailscale up`
left `docker` and `hardening` applied and the corrected re-run completed at
`ok=76 changed=28 failed=0`. No successor change is intended, so the waiver
names none: there is nothing outstanding to carry, only an observation that
cannot be manufactured.

The waiver covers that section alone. The other three additions were observed,
and a waiver of the whole change on the grounds that the next stage-6 execution
is an unscheduled company bootstrap is what an earlier draft of 6.2 attempted
and this task list already refused.

**6.3** The change's own branch and working tree were removed before this step,
so the archive was committed from a new branch cut from the freshly fetched
trunk at `416b80c` rather than from the branch #132 merged. Nothing is
discarded by that: the work is on the trunk, which is what the branch would
have been brought back to. `openspec validate --archived` passes.

Opening the record's own pull request, and removing the branch and working tree
once it merges, happen after the commit that writes this file, so they are
recorded here in prose rather than as tasks that could never be ticked in the
file containing them.
