## MODIFIED Requirements

### Requirement: Write Credentials Confined to the Gated Pipeline
Each environment's **Read & Write** Hetzner Cloud API token SHALL exist in exactly one location: that environment's own GitHub Environment secret, named `HCLOUD_TOKEN`. No such token SHALL be exported into a shell environment, written to a dotfile, `direnv` file, or any `.tfvars` file, or stored in a local credential helper on any workstation.

Local Terraform work SHALL authenticate with that environment's **Read Only** token — the one its declaration names as its read-only secret (see the Credential Scoping by Privilege requirement in the iac-cicd-pipeline capability) — which is sufficient for `terraform plan` and refresh and which causes any local `terraform apply` to fail at the Hetzner Cloud API. This states which token a workstation uses, not where the workstation obtains it.

Because the workspace's Execution Mode is Local, the destroy-policy gate, the saved-plan approval gate, and branch protection are properties of the GitHub Actions path to production rather than of Terraform itself — a workstation holding a write-capable token bypasses all three in a single command. This requirement extends the split established by the Credential Scoping by Privilege requirement in the iac-cicd-pipeline capability from CI jobs to workstations.

This holds of every environment, not of production alone. An environment whose GitHub Environment requires no reviewer is not thereby exempt: the reviewer and the credential confinement are independent properties, and an unreviewed environment's write token reaching a workstation is the same bypass with a smaller blast radius rather than a permitted one.

The prohibition SHALL be recorded where it is loaded without being sought: the repository README runbook for human operators, and a repository-root `AGENTS.md` for coding agents. **That record SHALL state the prohibition over every environment rather than naming one.** A record naming a single environment is read as silent about the others, which is the reading that matters here: an environment named nowhere in the record is one whose write token a reader has been given no reason to treat as confined, and the environment most likely to be omitted is the one added last.

#### Scenario: Local apply is refused by the API
- **WHEN** an operator or coding agent runs `terraform apply` from a workstation against any environment directory under `terraform/environments/`
- **THEN** the Hetzner Cloud API SHALL reject the write, because the only token available locally is that environment's read-only one

#### Scenario: Local plan remains available
- **WHEN** an operator runs `terraform plan` from a workstation against any environment directory under `terraform/environments/`
- **THEN** it SHALL succeed using that environment's read-only token, so that local iteration never requires write credentials

#### Scenario: A non-production environment's write token is confined identically
- **WHEN** an environment exists whose GitHub Environment requires no reviewer
- **THEN** its Read & Write token SHALL still exist only in that Environment's secrets, and SHALL NOT be available on any workstation

#### Scenario: An agent opening the repository is told the boundary
- **WHEN** a coding agent begins work in this repository
- **THEN** a repository-root `AGENTS.md` SHALL state that infrastructure changes reach Hetzner only through the gated pipeline and that `terraform apply` is not run locally

#### Scenario: The record covers an environment added after it was written
- **WHEN** an environment is added to `terraform/environments/`
- **THEN** the README runbook and `AGENTS.md` SHALL already state the prohibition in terms that cover it, rather than requiring an edit naming it before its write token is treated as confined
