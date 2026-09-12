terraform {
  required_version = ">= 1.9.0"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.52"
    }
  }

  # CLI-driven HCP Terraform workspace: state + locking only, no VCS
  # connection, no HCP-run execution. See the Remote State Backend
  # requirement (openspec/specs/iac-state-management/spec.md).
  #
  # The `main-staging` workspace's Execution Mode must be set to
  # Local in the HCP Terraform UI/API — that setting lives on the workspace,
  # not in this block, and it defaults to remote, so a workspace created and
  # not adjusted is misconfigured rather than merely unconfigured. Under
  # remote execution `terraform plan -out=tfplan` yields no locally
  # applicable plan file, which is what the saved-plan approval flow applies.
  #
  # The name is this stack's own: no two stacks share a
  # workspace, because a workspace holds one state and two stacks
  # sharing it would each plan the other's resources for destruction.
  #
  # It is NOT derived from this directory's name. The two agree, and they agree
  # by the convention in `docs/naming-conventions.md` rather than by any rule
  # here — read the production stack's `versions.tf` for that distinction, and
  # for why the HCP rename must come first and the `cloud` block second.
  cloud {
    organization = "shatynska"

    workspaces {
      name = "main-staging"
    }
  }
}

provider "hcloud" {
  # HCLOUD_TOKEN is read from the environment, and WHICH token that is
  # depends on the job:
  #
  #   - the apply job, which declares `environment: staging`, resolves
  #     that Environment's Read & Write token. That Environment requires no
  #     reviewer, so this is the one apply in this repository that reaches
  #     Hetzner without a human. What bounds it is the project boundary, not
  #     a gate: this token can destroy staging's project and can touch
  #     nothing in prod's (see the Each Environment Has a Dedicated Hetzner
  #     Cloud Project requirement, openspec/specs/iac-state-management/spec.md);
  #   - every other CI job declares no `environment:` and resolves a
  #     repository-scoped Read Only token, read as
  #     `secrets[<the name pipeline.yml declares>]` — for this stack
  #     HCLOUD_TOKEN_MAIN_STAGING, and for prod HCLOUD_TOKEN. A repository
  #     secret holds one value, which is why each stack needs a name of its
  #     own. (What it says about prod is wrong and is knowingly left so:
  #     prod declares a name of its own, and correcting this is
  #     `docs/change-queue.md` entry 70's work rather than a rename's.);
  #   - locally, whatever the operator exports for THIS directory, which is
  #     staging's Read Only token and is never the Read & Write one.
  #
  # See the Credential Scoping by Privilege requirement, and this directory's
  # own pipeline.yml, which is where the name lives.
}
