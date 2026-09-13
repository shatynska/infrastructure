## MODIFIED Requirements

### Requirement: HCP Terraform Access via a Static Token, Unsplit by Privilege
Authentication to HCP Terraform from GitHub Actions SHALL use a static HCP Terraform API token (`TF_API_TOKEN`), stored as an identical value in both the repository-scoped secret and the `main-production` Environment-scoped secret of the same name — kept as two separate GitHub secrets, not one shared name, so the environment-secret-shadowing mechanism stays wired up for a future privilege split.

GitHub OIDC dynamic credentials were the original design here, on the assumption that it could eliminate a long-lived HCP token the same way it can for a cloud provider. That assumption does not hold: HCP Terraform's dynamic-credentials / workload-identity feature authenticates a *provider* during a run HCP Terraform itself executes remotely — it has no mechanism for authenticating the Terraform CLI's own backend/state access when the CLI runs externally, as it does under this repository's CLI-driven, Local-execution workspace (see the Workspace Execution Mode Set to Local requirement). A follow-up attempt to split this token by privilege using HCP Terraform's per-team Plan/Write permission levels also failed: Teams are a paid-tier HCP Terraform feature, unavailable on this organization's free tier, where every token has full access to every workspace regardless of who it belongs to. Both findings were discovered during implementation (see design.md Decision 9).

This is a deliberately accepted risk, not an oversight. A compromised PR-time or drift-detection job holding `TF_API_TOKEN` can read or corrupt Terraform *state* — it cannot mutate real Hetzner infrastructure, because it still lacks the write-capable `HCLOUD_TOKEN`, which remains genuinely split by privilege (see the Credential Scoping by Privilege requirement in the iac-cicd-pipeline capability) and is the actual load-bearing security boundary in this design.

#### Scenario: HCP token cannot reach real infrastructure on its own
- **WHEN** a job holding only `TF_API_TOKEN` (no write-capable `HCLOUD_TOKEN`) is compromised
- **THEN** it SHALL be able to read or write Terraform state but SHALL NOT be able to create, modify, or destroy any Hetzner Cloud resource

#### Scenario: The split mechanism remains wired for a future upgrade
- **WHEN** this organization is upgraded to a paid HCP Terraform tier and team-scoped Plan/Write tokens become available
- **THEN** only the repository-scoped and environment-scoped `TF_API_TOKEN` secret *values* need to change to achieve a real privilege split — no workflow SHALL require code changes to adopt it
