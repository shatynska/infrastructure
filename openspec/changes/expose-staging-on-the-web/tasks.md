No specification deltas, so no derived tests are owed (`proposal.md`, "Capabilities"); the existing suites stay green.

## 1. Open the web ports at both layers

- [x] 1.1 Set `web_allowed_cidrs = ["0.0.0.0/0"]` in `terraform/stacks/main-staging/terraform.tfvars` and rewrite the comment above it to say why it is open and what listens. Correct the variable's description in `terraform/stacks/main-staging/variables.tf` ("empty is what staging ships with until…").
- [x] 1.2 Set `hardening_web_allowed_cidrs` to `["0.0.0.0/0"]` in `ansible/inventory/group_vars/staging.yml`. Rewrite the `EMPTY, AND EMPTY ON PURPOSE` paragraph; in `NARROWER THAN IT READS`, keep the mechanism, and reword its pointer to "the sentence above it", its "the whole of what refuses from the internet" and its pointer to `expose-staging-on-the-web` (design.md decision 3).

## 2. Correct what the opening falsifies

- [x] 2.1 `ansible/roles/hardening/README.md`: the sentence giving prod's and staging's `web_allowed_cidrs` values.
- [x] 2.2 `docs/bootstrap-a-new-host.md`, opening: the end-state bullet ("unreachable from the internet"), the *Time* paragraph's clause making stage 9 production's alone because of web exposure, and the prerequisites table's DNS row ("§4.4 says why not staging").
- [x] 2.3 §1.3's decision table: staging's `web_allowed_cidrs` cell (`[]` — "until something is deployed there").
- [x] 2.4 §4.4, per design.md decision 4: rewrite the opening instruction and replace "Do not point a hostname at the staging server"; in `shatynska.com`'s table add `staging` A and correct the `fuperia` row; add the dated `fincci.bike` table with exactly the rows decision 4 lists and its nameservers in prose; make "This table is the project's only written record" plural; rewrite the revisit trigger, keeping mail moving off either zone.
- [x] 2.5 "From here on, two hosts" (after §4.4): the "What still differs" bullet "Staging has no way in from the internet".
- [x] 2.6 Stage 6: the `hardening_web_allowed_cidrs` table row and the UFW check paragraph ("production shows 80 and 443, staging shows neither").
- [x] 2.7 Appendix B: "What staging has no need to rebuild is a DNS record or a certificate, having neither" — a staging whose address changed now owes the `*.main-staging.fincci.bike` edit (§4.4), and its certificates reissue on their own.
- [x] 2.8 Appendix C: staging "has no hostname, no certificate and no open web port until `docs/backlog.md`'s staging-web-exposure entry does".
- [x] 2.9 `README.md`: the stack-adding list's "For staging, `docs/backlog.md` records what that half still needs". Its "What staging is *not*, yet" paragraph stays with `docs/backlog.md`'s `refresh-staging-group-vars-banner`, which already quotes it; add to that entry that its third claim, "no DNS records", is now false too.
- [x] 2.10 `docs/backlog.md`'s `say-what-the-host-firewall-actually-gates`: its quotation of bootstrap's "both firewall layers refuse inbound traffic to them" (rewritten by 2.2 and 2.5) and "staging reaches no public web port". Its sentence citing `expose-staging-on-the-web` waits for 4.3.
- [x] 2.11 `docs/backlog.md`: append an entry recording the `<service>.<server>.<base domain>` hostname rule for `docs/naming-conventions.md`.

## 3. Verify

- [x] 3.1 In `terraform/stacks/main-staging`: `terraform fmt -check`, `terraform validate` and `tflint`. A local `terraform plan` is attempted with the read-only token; where it cannot run, say why, and let the pull request's plan comment stand in (4.1).
- [x] 3.2 `ansible-lint` and `ansible-playbook --syntax-check`; `python3 -m unittest discover --start-directory .github/tests`; `openspec validate --all`.
- [x] 3.3 Re-run `git grep -n -i -E 'web_allowed_cidrs|80/443|port 443|web port|staging-web-exposure|expose-staging-on-the-web|no (public )?(DNS|hostname)|no certificate|unreachable from the internet|no way in' -- ':!openspec/changes'` and confirm each remaining hit is true after this change, or is 4.3's.

## 4. Ship

- [ ] 4.1 Open the pull request; its plan comment for `main-staging` shows `hcloud_firewall` updated in place with two added rules and nothing replaced or destroyed. Operator confirms the merge, and that staging's apply and staging's converge are green.
- [ ] 4.2 Confirm per design.md decision 5 from the operator's workstation, and record the outputs here.
- [ ] 4.3 Archive on the freshly fetched trunk: delete `docs/backlog.md`'s `expose-staging-on-the-web`, and correct `say-what-the-host-firewall-actually-gates`'s sentence citing it.

## Verification record

**3.1**, run 2026-09-15 in this change's working tree. `terraform fmt -check` passes. `terraform init -backend=false` then `terraform validate`: "Success! The configuration is valid." `tflint`: exit 0, no findings. **A local `terraform plan` did not run.** The workstation's HCP Terraform credential belongs to the `fuperia` organization alone — the HCP API's `/organizations` returned `['fuperia']` on 2026-09-14 — so `terraform init` against this stack's `cloud` block fails with `organization "shatynska" at host app.terraform.io not found`. The pull request's plan comment is the plan check (4.1).

**3.2.** `pre-commit run --files` over the seven changed files: Terraform fmt, Terraform validate with tflint, Terraform validate, gitleaks and ansible-lint passed; `ansible-playbook --syntax-check` skipped, since no playbook changed. `python3 -m unittest discover --start-directory .github/tests`: 1210 tests, OK. `openspec validate --all`: 11 passed, 0 failed.

**3.3.** Every remaining hit is true after this change, or belongs elsewhere:
- `README.md`'s "What staging is *not*, yet" belongs to `refresh-staging-group-vars-banner` (2.9).
- `docs/backlog.md`'s `expose-staging-on-the-web` is deleted by 4.3.
- `check-public-endpoints-from-outside` concerns production's gating.
- `record-how-an-application-is-onboarded` describes a host without DNS in general.
- The hits in the `hardening` role's defaults, its Molecule scenarios, `terraform/modules/server` and the production stack's files describe the role's, the module's or production's own values, not staging's.

One hit found by the sweep was corrected: `say-what-the-host-firewall-actually-gates` introduced its 2026-09-13 measurement with staging's CIDRs in the present tense ("is `[]`"), and now says "was `[]` at the time".

## Code review record

One round of `ai-toolkit:change-code-reviewer`, on 2026-09-15, reviewed `4315b3c..f57e2d2`. It found the Terraform and Ansible changes correct. It probed public DNS, production's routers and staging's listeners, all read-only, and they matched what §4.4 records. It could not probe `sudo ufw status`, since `ops-claude` has no sudo, so stage 6's "each shows 80 and 443 allowed" was left unprobed. It raised four documentation findings, all fixed in the commit that follows:

1. **Medium.** §4.4's `fincci.bike` table missed `main-staging.fincci.bike` and `main-production.fincci.bike`. Each is an A record of its own, because a wildcard does not match the name it sits under. Re-measured over `dns.google`: they resolve to `62.238.17.177` and `2.29.14.98`, and a non-existent name returns NXDOMAIN, so there is no `*.fincci.bike`. Both rows were added, the `ops` row's "the one record" claim was dropped, and design.md decision 4 was corrected to match.
2. **Medium.** Appendix B's new DNS sentence contradicted the paragraph's own stale ending, which said a staging rebuild stops at 6.3 "having no stack to redeploy" and was already false against "then through stage 7". That ending was deleted, and the DNS sentence now names every staging row in §4.4.
3. **Low.** The "Revisit when" paragraph had lost decision 4's address-change trigger. It is restored, and the cost sentence now says "every record pointing at that server".
4. **Low.** `refresh-staging-group-vars-banner` credited this change with making "no DNS records" false. It now credits the operator, who created the records, which this change only recorded.

The fixes were not re-reviewed: they are small documentation corrections, below AGENTS.md's bar of "substantial enough to warrant it". After them, `.github/tests` passed (1210 tests OK), `openspec validate --all` passed (11), and pre-commit passed over the edited files.
