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
  # The `main-production` workspace's Execution Mode must be set to
  # Local in the HCP Terraform UI/API — that setting lives on the workspace,
  # not in this block.
  #
  # THE WORKSPACE NAME AND THIS DIRECTORY'S NAME AGREE, AND THAT IS A
  # CONVENTION RATHER THAN A RULE. *Remote State Backend*
  # (openspec/specs/iac-state-management/spec.md) forbids COMPUTING one from
  # the other and explicitly permits the two to agree;
  # `docs/naming-conventions.md` is the convention under which they do. Nothing
  # here derives one name from the other, and nothing may — the two are renamed
  # by different mechanisms, so a derivation would be false for the interval
  # between them.
  #
  # RENAMING THIS WORKSPACE HAPPENS IN THE HCP INTERFACE FIRST AND IN THIS
  # BLOCK SECOND, and the order is not reversible. `terraform init` CREATES a
  # workspace it cannot find rather than failing, so pushing the new name first
  # leaves an empty workspace holding the name the rename needed. That
  # requirement carries what such a workspace does and does not do; it is
  # stated there rather than repeated here, because it was once stated wrongly
  # in both places at once.
  cloud {
    organization = "shatynska"

    workspaces {
      name = "main-production"
    }
  }
}

provider "hcloud" {
  # HCLOUD_TOKEN is read from the environment, and WHICH token that is
  # depends on the job:
  #
  #   - the gated apply job, which declares `environment: main-production`,
  #     resolves that Environment's Read & Write token;
  #   - every other CI job declares no `environment:` and resolves a
  #     repository-scoped Read Only token — but NOT by this name. It is
  #     read as `secrets[<the name pipeline.yml declares>]`, which for
  #     this stack is HCLOUD_TOKEN_MAIN_PRODUCTION and for every other
  #     stack is a name of its own. A repository secret holds one value,
  #     so each stack needs a read-only secret of its own.
  #
  #     THE ONE NAME IT MAY NOT BE IS `HCLOUD_TOKEN`, and that is the
  #     whole reason this bullet spells the name out. Every stack's
  #     GitHub Environment defines `HCLOUD_TOKEN` as that stack's Read &
  #     Write token, and GitHub resolves an Environment-scoped secret
  #     ahead of a repository-scoped one of the same name — so a job
  #     that declares an `environment:` and reads `HCLOUD_TOKEN` gets
  #     the WRITE token, silently, from a field that says read-only.
  #     pipeline.yml carries the full argument beside the declaration.
  #   - locally, whatever the operator exports, which is the Read Only
  #     token and is never the Read & Write one.
  #
  # See the Credential Scoping by Privilege requirement, and this
  # directory's own pipeline.yml, which is where the name now lives.
}
