# modules/server's two new inputs: the `tenant` label axis, and the firewall's
# name, which this module stops deriving.
#
# Derived from the delta specs of the OpenSpec change
# `rename-the-stacks-and-their-resources`, before any implementation of it
# existed. The path those deltas sit at is not written here: a change's
# artifacts move when it is archived, and this repository's citation convention
# is to name the change and the artifact in prose instead. See that change's
# `test-plan.md` for the scenario-to-test mapping, the recorded baseline, and
# the per-assertion classification.
#
# The requirement is *Consistent Resource Labeling*
# (openspec/specs/iac-safety-hardening/spec.md), whose scenarios "Prod
# resources are labeled" and "Prod volume is labeled" now name three labels
# rather than two, and whose new paragraph states that each axis SHALL be its
# own label "rather than a segment of a name".
#
# WHY THE FIREWALL'S NAME IS TESTED IN THE SAME FILE AS A LABEL
# -------------------------------------------------------------
# Because they are one decision read from two sides. The module builds
# `name = "${var.environment}-${var.name}"` today, which is the axis-as-name-
# segment the labeling requirement's new paragraph forbids, and which this
# change's design.md decision 4 replaces with an input of its own. The label
# assertions below establish that the axis is carried as a label; the firewall
# assertions establish that it stopped being carried as a name.
#
# WHY THE VALUES BELOW ARE NOT THE ONES THE STACKS WILL USE
# ----------------------------------------------------------
# `tenant = "acme"` and `firewall_name = "gateway"` are deliberately NOT `main`,
# and `environment`/`name` are deliberately the values the real stack takes.
# A fixture using the production values cannot tell a plumbed-through input from
# a hardcoded literal, and cannot tell `firewall_name` from any expression over
# `environment` and `name` -- which is the substitution these assertions exist
# to rule out.
#
# mock_provider avoids any real Hetzner API call -- see creation.tftest.hcl for
# the shared rationale. This file is `command = plan` throughout and never
# touches real infrastructure.

mock_provider "hcloud" {}

variables {
  environment       = "production"
  name              = "main-production"
  server_type       = "cx22"
  image             = "ubuntu-24.04"
  location          = "fsn1"
  ssh_key_id        = "12345"
  ssh_allowed_cidrs = ["203.0.113.0/24"]
  tenant            = "acme"
  firewall_name     = "gateway"
}

# SPECIFIED -- "Every `hcloud_*` resource managed by this repository SHALL carry
# a `managed_by = "terraform"` label and one label per axis its stack is
# identified on: an `environment` label ... and a `tenant` label naming the
# tenant", and scenario "Prod resources are labeled", whose THEN now reads
# `environment = "production"`, `tenant = "main"` and
# `managed_by = "terraform"`. The values there are the stack's; what this module
# owes is that each label is applied from its own input, which is what the
# non-production values above establish.
run "plan_applies_the_tenant_label_to_every_resource_the_module_creates" {
  command = plan

  assert {
    condition     = hcloud_server.this.labels["tenant"] == var.tenant
    error_message = "hcloud_server.this did not carry a tenant label taken from var.tenant -- the tenant axis is either missing or hardcoded, and a hardcoded one is a module a second tenant cannot use"
  }

  assert {
    condition     = hcloud_firewall.this.labels["tenant"] == var.tenant
    error_message = "hcloud_firewall.this did not carry a tenant label taken from var.tenant -- a resource this module creates is inside the labeling obligation whether or not it is the server"
  }

  assert {
    condition     = hcloud_server.this.labels["environment"] == var.environment
    error_message = "hcloud_server.this lost its environment label while gaining a tenant one -- the axes are additive, not alternatives"
  }

  assert {
    condition     = hcloud_server.this.labels["managed_by"] == "terraform"
    error_message = "hcloud_server.this lost its managed_by=terraform label while gaining a tenant one"
  }
}

# DERIVED -- no scenario states the merge order. It mirrors the existing
# `labels.tftest.hcl` assertion for `environment`, and the failure it catches is
# the same one: a caller-supplied label silently replacing an axis, which plans
# and applies and is visible only in the Hetzner console.
run "plan_a_caller_supplied_label_does_not_overwrite_the_tenant_axis" {
  command = plan

  variables {
    labels = {
      team   = "platform"
      tenant = "not-the-tenant"
    }
  }

  assert {
    condition     = hcloud_server.this.labels["tenant"] == var.tenant
    error_message = "a caller-supplied `tenant` label overrode the axis label this module applies -- `var.labels` must be merged UNDER the automatic labels, not over them"
  }

  assert {
    condition     = hcloud_server.this.labels["team"] == "platform"
    error_message = "hcloud_server.this did not merge a caller-supplied label alongside the axis labels"
  }
}
