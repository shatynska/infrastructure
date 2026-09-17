## Why

`configure-the-staging-host` rewrote `docs/bootstrap-a-new-host.md`'s stage 6 into a stage run once per environment, and then — for the first time since that document was written — someone followed it end to end against a host that did not yet exist. Four things went wrong that the document does not mention, and each cost time that a sentence would have saved.

The document was accurate. What it was not is complete about the paths a procedure takes when it does not go smoothly: a tool that is not installed, a converge that fails partway, advice that produces a false reading, and a credential that cannot be checked before it is relied on.

**The four findings do not all rest on the same kind of evidence, and saying so matters in a change about documentary accuracy.** Two of them are behavioural, and rest on `configure-the-staging-host`'s converge, recorded under `## Verification record` in that change's archived task list: the partial converge and its recovery (10.2), and production's `changed=2` under `--check` with its fixture reproduction (10.1). Those are the first observations this document has ever had — every previous revision was written from the repository outward, from what the code does, and reviewed the same way.

The other two are **documentary**, and rest on nothing but reading the committed files. §4.1 offers a `source` fallback and §6.0 does not; §6.1 offers no way to check the token it tells you to create. Both are visible by inspection, need no run to establish, and would have been just as true had the converge gone perfectly. What the session supplied was the occasion to notice them — a machine without direnv, and a `401` that turned out to be a truncated paste — not the evidence that they are gaps.

## What Changes

- **§6.0 gains the `source` fallback that §4.1 already has.** It currently ends at `direnv allow` with no alternative, as does `ansible/.envrc.example`, which is the file the operator copies at that exact step. §4.1 offers `source` for Terraform's `.envrc` and warns why it is risky there. For `ansible/.envrc` it is *not* risky, and that asymmetry is worth stating rather than leaving the reader to infer: sourcing Terraform's leaks `HCLOUD_TOKEN` across environments, while Ansible's two variables collide with nothing and mean the same thing in any directory. §4.1 already states that immunity, at the point where it is explaining the *hazard*; §6.0 is where the fallback is offered and where a reader needs it, and it is silent.
- **§6.3 gains what to do when the converge fails partway**, which it presently does not admit can happen. Two facts are needed and neither is written down: the `tailscale up` task carries `no_log: true`, so its failure is reported as `"censored": "the output has been hidden…"` and the real error must be obtained by running `tailscale up --authkey=…` by hand on the host; and a failed run leaves a **partially-converged** host whose correct recovery is to fix the input and re-run, every role being idempotent.
- **§6.3 stops recommending `--check --diff` without qualification.** It says the flag "is useful on every run after the first". It is, but two `tailscale` tasks report `changed` on every check-mode run forever — `get_url` with no `checksum:` cannot confirm a file matches without downloading it, and check mode will not. An operator following that sentence reads drift on a healthy host. The reading is the doc's fault, not the operator's.

  **Described rather than repaired, deliberately.** `docs/change-queue.md` entry 23 already owns the fix, enumerates three candidate remedies, and states that whatever shape it takes must not ship a drift signal whose baseline is two. Settling that trade-off here would resolve it inside another change's scope, and would leave the document wrong in the meantime either way.
- **§6.1 gains a way to check the GHCR token before relying on it.** One request against `api.github.com/user` returns both validity and scopes. The run that prompted this change spent several exchanges on a `401` that turned out to be a truncated paste, and the doc's only guidance is to create the token and paste it.

### Not in scope

The three roles' behaviour is unchanged, and so is the play. Nothing here alters what a converge does — only what the document says about doing one. `README.md`'s "`direnv allow` is not optional" sentence is in scope, and so is `ansible/.envrc.example`'s header: both carry the same defect as §6.0 and were written by the same change, and the example file is the one an operator has open at the moment the fallback is needed. Applying the scope rule to one and not the others would be arbitrary.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None, and `.openspec.yaml` therefore carries `skip_specs: true` — the established form here, used by four archived changes, and the case `AGENTS.md` names for it. Every fact this change writes down is already true of the mechanisms as they stand; no mechanism moves.

**Two of the four findings touch mechanisms that specifications govern, and still owe no delta — but not for the reason first written here.** Neither the `no_log` masking nor `get_url`'s check-mode reporting is obliged by any requirement in this repository: a grep of `openspec/specs/` for `no_log`, `masked` and `censored` returns nothing, and no requirement mentions check mode at all. The masking is the role's own decision, stated in its comment; the check-mode behaviour is a property of an Ansible module. There is no requirement to modify because there is no requirement on the point.

## Impact

**Documentation.** `docs/bootstrap-a-new-host.md` §6.0, §6.1 and §6.3, `README.md`'s local-setup step 4, and `ansible/.envrc.example`'s header.

**Records.** `docs/change-queue.md` entry 23 gains one line. It already carries the check-mode finding, recorded by `configure-the-staging-host` when the production run produced it; this change is where the same fact reaches the operator-facing document — and that creates a coupling running one way only. §6.3 will point at entry 23, and entry 23 will not know a document now states a baseline of two. When it pins a `checksum:` or replaces `get_url`, §6.3 would silently begin telling operators that two changed tasks are healthy on a host where zero is correct: a slow falsehood in the canonical bootstrap document, of exactly the class this change exists to remove.

The line belongs to **this** change rather than to entry 23, because this is the change creating the dependency — before it merges, nothing asserts that baseline, so entry 23's implementer could not discover it. The repository has the precedent: `configure-the-staging-host` task 8.5 wrote the reciprocal of an ordering line into a neighbouring entry for the same reason.

**Not touched.** `terraform/`, `platform/`, `.github/`, and every executable file under `ansible/` — the one file touched there is a committed `.example` header, which no tool reads. No credential, no host, no pipeline.

**Verification.** The static suite and the pre-commit hooks, neither of which reads prose for truth — so they establish the citation form and the repository's conventions, and nothing about whether a sentence is correct. What carries the behavioural claims is the archived record cited above; what carries the documentary ones is that the reader can check them against the committed files in a minute.

Three of the four additions are also **directly observable now**, against the staging host that already exists, and the change proposes them as its confirmation gate rather than waiving it.
