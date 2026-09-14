No specification deltas, so no derived tests are owed (`proposal.md`, "Capabilities"); the existing suites stay green.

## 1. Open the web ports at both layers

- [ ] 1.1 Set `web_allowed_cidrs = ["0.0.0.0/0"]` in `terraform/stacks/main-staging/terraform.tfvars` and rewrite the comment above it to say why it is open and what listens. Correct the variable's description in `terraform/stacks/main-staging/variables.tf` ("empty is what staging ships with until…").
- [ ] 1.2 Set `hardening_web_allowed_cidrs` to `["0.0.0.0/0"]` in `ansible/inventory/group_vars/staging.yml`. Rewrite the `EMPTY, AND EMPTY ON PURPOSE` paragraph; in `NARROWER THAN IT READS`, keep the mechanism, and reword its pointer to "the sentence above it", its "the whole of what refuses from the internet" and its pointer to `expose-staging-on-the-web` (design.md decision 3).

## 2. Correct what the opening falsifies

- [ ] 2.1 `ansible/roles/hardening/README.md`: the sentence giving prod's and staging's `web_allowed_cidrs` values.
- [ ] 2.2 `docs/bootstrap-a-new-host.md`, opening: the end-state bullet ("unreachable from the internet"), the *Time* paragraph's clause making stage 9 production's alone because of web exposure, and the prerequisites table's DNS row ("§4.4 says why not staging").
- [ ] 2.3 §1.3's decision table: staging's `web_allowed_cidrs` cell (`[]` — "until something is deployed there").
- [ ] 2.4 §4.4, per design.md decision 4: rewrite the opening instruction and replace "Do not point a hostname at the staging server"; in `shatynska.com`'s table add `staging` A and correct the `fuperia` row; add the dated `fincci.bike` table with exactly the rows decision 4 lists and its nameservers in prose; make "This table is the project's only written record" plural; rewrite the revisit trigger, keeping mail moving off either zone.
- [ ] 2.5 "From here on, two hosts" (after §4.4): the "What still differs" bullet "Staging has no way in from the internet".
- [ ] 2.6 Stage 6: the `hardening_web_allowed_cidrs` table row and the UFW check paragraph ("production shows 80 and 443, staging shows neither").
- [ ] 2.7 Appendix B: "What staging has no need to rebuild is a DNS record or a certificate, having neither" — a staging whose address changed now owes the `*.main-staging.fincci.bike` edit (§4.4), and its certificates reissue on their own.
- [ ] 2.8 Appendix C: staging "has no hostname, no certificate and no open web port until `docs/backlog.md`'s staging-web-exposure entry does".
- [ ] 2.9 `README.md`: the stack-adding list's "For staging, `docs/backlog.md` records what that half still needs". Its "What staging is *not*, yet" paragraph stays with `docs/backlog.md`'s `refresh-staging-group-vars-banner`, which already quotes it; add to that entry that its third claim, "no DNS records", is now false too.
- [ ] 2.10 `docs/backlog.md`'s `say-what-the-host-firewall-actually-gates`: its quotation of bootstrap's "both firewall layers refuse inbound traffic to them" (rewritten by 2.2 and 2.5) and "staging reaches no public web port". Its sentence citing `expose-staging-on-the-web` waits for 4.3.
- [ ] 2.11 `docs/backlog.md`: append an entry recording the `<service>.<server>.<base domain>` hostname rule for `docs/naming-conventions.md`.

## 3. Verify

- [ ] 3.1 In `terraform/stacks/main-staging`: `terraform fmt -check`, `terraform validate` and `tflint`. A local `terraform plan` is attempted with the read-only token; where it cannot run, say why, and let the pull request's plan comment stand in (4.1).
- [ ] 3.2 `ansible-lint` and `ansible-playbook --syntax-check`; `python3 -m unittest discover --start-directory .github/tests`; `openspec validate --all`.
- [ ] 3.3 Re-run `git grep -n -i -E 'web_allowed_cidrs|80/443|port 443|web port|staging-web-exposure|expose-staging-on-the-web|no (public )?(DNS|hostname)|no certificate|unreachable from the internet|no way in' -- ':!openspec/changes'` and confirm each remaining hit is true after this change, or is 4.3's.

## 4. Ship

- [ ] 4.1 Open the pull request; its plan comment for `main-staging` shows `hcloud_firewall` updated in place with two added rules and nothing replaced or destroyed. Operator confirms the merge, and that staging's apply and staging's converge are green.
- [ ] 4.2 Confirm per design.md decision 5 from the operator's workstation, and record the outputs here.
- [ ] 4.3 Archive on the freshly fetched trunk: delete `docs/backlog.md`'s `expose-staging-on-the-web`, and correct `say-what-the-host-firewall-actually-gates`'s sentence citing it.
