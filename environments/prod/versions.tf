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
  #
  # TODO(task 1.1): replace the placeholder organization name below once
  # the HCP Terraform organization has been created.
  cloud {
    organization = "REPLACE_WITH_HCP_ORGANIZATION"

    workspaces {
      name = "infrastructure-prod"
    }
  }
}

provider "hcloud" {
  # HCLOUD_TOKEN is read from the environment (repository-scoped Read
  # Only token locally and in PR/scheduled CI jobs; the production
  # Environment-scoped Read & Write token only in the gated apply job).
  # See the Credential Scoping by Privilege requirement.
}
