# modules/volume's new `tenant` label axis.
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
# (openspec/specs/iac-safety-hardening/spec.md), scenario "Prod volume is
# labeled", whose THEN now names three labels rather than two.
#
# `tenant = "acme"` is deliberately not `main`: a fixture carrying the value the
# stacks will pass cannot tell an input that is plumbed through from a literal
# the module hardcodes, and a hardcoded label value is a module a second tenant
# cannot use.
#
# mock_provider avoids any real Hetzner API call -- see creation.tftest.hcl for
# the shared rationale. `command = plan` throughout.

mock_provider "hcloud" {}

variables {
  environment = "production"
  name        = "main"
  size        = 10
  server_id   = "12345"
  tenant      = "acme"
}

# SPECIFIED -- "one label per axis its stack is identified on: an `environment`
# label naming the environment its stack belongs to, and a `tenant` label naming
# the tenant", and scenario "Prod volume is labeled".
run "plan_applies_the_tenant_label_alongside_the_existing_axes" {
  command = plan

  assert {
    condition     = hcloud_volume.this.labels["tenant"] == var.tenant
    error_message = "hcloud_volume.this did not carry a tenant label taken from var.tenant -- the tenant axis is either missing or hardcoded"
  }

  assert {
    condition     = hcloud_volume.this.labels["environment"] == var.environment
    error_message = "hcloud_volume.this lost its environment label while gaining a tenant one -- the axes are additive, not alternatives"
  }

  assert {
    condition     = hcloud_volume.this.labels["managed_by"] == "terraform"
    error_message = "hcloud_volume.this lost its managed_by=terraform label while gaining a tenant one"
  }
}

# DERIVED -- no scenario states the merge order; it mirrors the assertion
# `labels.tftest.hcl` already makes for `environment`, and mirrors
# modules/server's `locals.labels = merge({...}, var.labels)` pattern this
# module is written to follow.
run "plan_a_caller_supplied_label_does_not_overwrite_the_tenant_axis" {
  command = plan

  variables {
    labels = {
      tenant = "not-the-tenant"
    }
  }

  assert {
    condition     = hcloud_volume.this.labels["tenant"] == var.tenant
    error_message = "a caller-supplied `tenant` label overrode the axis label this module applies -- `var.labels` must be merged UNDER the automatic labels, not over them"
  }
}

# DERIVED -- tasks.md 2.3 ("the same `tenant` variable"), which makes
# modules/server's tasks.md 2.1 validation ("validated non-empty the way
# `environment` is") this module's obligation too. A blank value is accepted by
# Hetzner and produces a volume in no tenant group at all.
run "plan_rejects_empty_tenant" {
  command = plan

  variables {
    tenant = ""
  }

  expect_failures = [
    var.tenant,
  ]
}

run "plan_rejects_blank_tenant" {
  command = plan

  variables {
    tenant = "   "
  }

  expect_failures = [
    var.tenant,
  ]
}
