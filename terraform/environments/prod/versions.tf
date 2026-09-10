terraform {
  required_version = ">= 1.9.0"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.52"
    }
  }

  # CLI-driven HCP Terraform workspace: state + locking only, no VCS
  # connection, no HCP-run execution. See design.md Decision 1.
  #
  # The `infrastructure-prod` workspace's Execution Mode must be set to
  # Local in the HCP Terraform UI/API (task 1.2) — that setting lives on
  # the workspace, not in this block.
  cloud {
    organization = "shatynska"

    workspaces {
      name = "infrastructure-prod"
    }
  }
}

provider "hcloud" {
  # HCLOUD_TOKEN is read from the environment, and WHICH token that is
  # depends on the job:
  #
  #   - the gated apply job, which declares `environment: production`,
  #     resolves that Environment's Read & Write token;
  #   - every other CI job declares no `environment:` and resolves a
  #     repository-scoped Read Only token — but not by this name. It is
  #     read as `secrets[<the name pipeline.yml declares>]`, which for
  #     this environment is `HCLOUD_TOKEN` and for a second environment
  #     will not be. A repository secret holds one value, so each
  #     environment needs a read-only secret of its own;
  #   - locally, whatever the operator exports, which is the Read Only
  #     token and is never the Read & Write one.
  #
  # See the Credential Scoping by Privilege requirement, and this
  # directory's own pipeline.yml, which is where the name now lives.
}
