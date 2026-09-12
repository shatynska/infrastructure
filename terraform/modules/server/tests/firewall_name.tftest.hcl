# modules/server stops deriving the firewall's name.
#
# Derived from the delta specs of the OpenSpec change
# `rename-the-stacks-and-their-resources`, before any implementation of it
# existed. The path those deltas sit at is not written here: a change's
# artifacts move when it is archived, and this repository's citation convention
# is to name the change and the artifact in prose instead. See that change's
# `test-plan.md` for the scenario-to-test mapping, the recorded baseline, and
# the per-assertion classification.
#
# The specification this traces to is *Consistent Resource Labeling*
# (openspec/specs/iac-safety-hardening/spec.md), whose new paragraph states that
# each axis SHALL be its own label "rather than a segment of a name". The
# module's `name = "${var.environment}-${var.name}"` is exactly an axis carried
# as a name segment, and after this change it would read
# `production-main-production`.
#
# SEPARATE FILE FROM `tenant_label.tftest.hcl` ON PURPOSE. Terraform skips every
# remaining `run` in a file once one fails, and both files are red until the
# implementation lands -- so a single file would report the label failure and
# say nothing about the firewall's name until the labels were fixed.
#
# WHY THE VALUES BELOW ARE NOT THE ONES THE STACKS WILL USE. `firewall_name`
# is deliberately NOT `main`, while `environment` and `name` are the values the
# production stack will carry. A fixture whose firewall name is derivable from
# its other inputs cannot tell an input that is read from an expression that
# happens to produce the same string, which is the substitution these assertions
# exist to rule out.
#
# mock_provider avoids any real Hetzner API call -- see creation.tftest.hcl for
# the shared rationale. `command = plan` throughout.

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

# DERIVED -- design.md decision 4 of this change: "The firewall's name becomes a
# required input, `firewall_name` ... neither derived from `tenant` nor
# defaulted to `main`". No scenario states a firewall's name; what the
# specification states is the general rule the derivation offends.
#
# The two assertions are the same proposition stated twice on purpose: the first
# is the obligation, the second names the exact expression being retired, so a
# failing run says WHICH substitution happened rather than only that the name
# was wrong.
run "plan_the_firewall_takes_its_name_from_its_own_input" {
  command = plan

  assert {
    condition     = hcloud_firewall.this.name == var.firewall_name
    error_message = "hcloud_firewall.this.name is not var.firewall_name -- the firewall's name is an input of its own, which is also what lets a second firewall in one stack be named beside the first"
  }

  assert {
    condition     = hcloud_firewall.this.name != "${var.environment}-${var.name}"
    error_message = "hcloud_firewall.this.name is still `${var.environment}-${var.name}` -- the derivation this change retires, which after the rename reads `production-main-production`: the stack's name with its environment half in front of it"
  }
}

# DERIVED -- design.md decision 4 rejects `name = var.tenant` by name: it
# "produces the right string today and asserts something false", that a stack
# has one firewall and that its name is the tenant's. Asserted separately from
# the assertion above because a module that swapped one derivation for the other
# would satisfy the second assertion there and still not take the input.
run "plan_the_firewall_name_is_not_derived_from_the_tenant_either" {
  command = plan

  assert {
    condition     = hcloud_firewall.this.name != var.tenant
    error_message = "hcloud_firewall.this.name is var.tenant -- a second derivation replacing the first. The rank axis exists precisely so a second firewall can be named beside the first, and a derivation forecloses that"
  }
}

# DERIVED -- tasks.md 2.2: `firewall_name` is "validated non-empty, with no
# default", the way `environment` already is. A firewall named by an empty
# string is a Hetzner resource an operator cannot find in the console, and the
# provider's own error names neither the variable nor the module.
run "plan_rejects_empty_firewall_name" {
  command = plan

  variables {
    firewall_name = ""
  }

  expect_failures = [
    var.firewall_name,
  ]
}

run "plan_rejects_blank_firewall_name" {
  command = plan

  variables {
    firewall_name = "   "
  }

  expect_failures = [
    var.firewall_name,
  ]
}
