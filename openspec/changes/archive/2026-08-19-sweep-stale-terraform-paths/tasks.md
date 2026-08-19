## 1. Sweep stale path references

- [x] 1.1 Update `openspec/specs/iac-cicd-pipeline/spec.md`: `environments/` → `terraform/environments/`, `modules/` → `terraform/modules/` (lines 10, 29, 33, 42, 49, 95 as of this proposal)
- [x] 1.2 Update `openspec/specs/iac-safety-hardening/spec.md`: same substitutions (lines 10, 21, 30, 57, 61, 74, 78 as of this proposal)
- [x] 1.3 Update `openspec/specs/iac-state-management/spec.md`: same substitutions (lines 11, 15, 24, 52 as of this proposal)
- [x] 1.4 Update `openspec/specs/iac-repo-foundations/spec.md`'s "Version Control Excludes State and Secrets" requirement only (lines 70, 80 as of this proposal) — leave the "Environment and Module Folder Structure" requirement (lines 7-19) untouched, since `integrate-ansible-host-config`'s own delta spec already covers it

## 2. Verification

- [x] 2.1 Re-run the greps from this change's `design.md`/proposal research (`grep -n "environments/\|modules/"` across the four files) and confirm every remaining hit is either already `terraform/environments/`\`terraform/modules/`, or a non-path use of the word "modules"
- [x] 2.2 `openspec validate --change sweep-stale-terraform-paths --strict` passes
