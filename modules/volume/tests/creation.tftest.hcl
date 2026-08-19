# Tests for modules/volume's core creation behavior, derived from the
# add-prod-data-volume change's delta specs:
#   - specs/iac-data-volumes/spec.md, "Conditional Prod Volume Creation"
#     (Scenario: Toggle enabled creates the volume)
#   - specs/iac-data-volumes/spec.md, "Volume Attached to Prod Server at
#     Creation" (Scenario: Volume is created already attached)
#
# These run blocks exercise modules/volume in isolation (not
# environments/prod), given a server_id as if the prod server were already
# enabled. They do NOT exercise the environments/prod-level
# `count = var.volume_enabled && var.server_enabled` coupling itself --
# that composition lives outside this module and outside this test-path
# glob. See test-manifest.md for what that means for scenario coverage.
#
# mock_provider replaces the real hcloud provider so no Hetzner API call or
# credential is required to run these tests (command = plan only, per the
# dispatch instruction -- no real infrastructure is ever touched).
#
# Assertions are limited to attributes the module sets directly from its
# own input variables (name, size, server_id, delete_protection) -- never
# on provider-computed-only attributes (id, linux_device, location), whose
# plan-time value cannot be asserted on here without relying on unverified
# mock-provider unknown-value semantics. See test-manifest.md for why
# "Volume shares the server's location" is recorded as uncovered.
#
# hcloud_volume.server_id is a `number` in the real hcloud provider schema
# (verified directly against the installed hetznercloud/hcloud provider),
# even though this module's own `server_id` variable is expected to be
# typed `string` per tasks.md 1.2 -- Terraform converts the numeric string
# automatically when it's assigned to the resource argument, so the
# assertions below use tonumber() only to compare like with like.

mock_provider "hcloud" {}

variables {
  environment       = "prod"
  name              = "production_data"
  size              = 10
  server_id         = "12345"
  delete_protection = true
}

run "plan_creates_volume_with_declared_configuration" {
  command = plan

  assert {
    condition     = hcloud_volume.this.name == var.name
    error_message = "hcloud_volume.this.name did not match the declared volume name"
  }

  assert {
    condition     = hcloud_volume.this.size == var.size
    error_message = "hcloud_volume.this.size did not match the declared volume size"
  }
}

run "plan_attaches_to_server_at_creation" {
  command = plan

  assert {
    condition     = hcloud_volume.this.server_id == tonumber(var.server_id)
    error_message = "hcloud_volume.this.server_id was not set from the given server_id -- the volume would not be attached to the server at creation"
  }
}

# DERIVED (not a delta-spec scenario, but directly grounded in
# design.md Decision 3: "modules/volume never supplies `location`... so
# `server_id` must always be non-null whenever the volume is created").
# A future implementer must make this pass by declaring `server_id` as
# `nullable = false` with a non-empty validation, or equivalent -- this is
# not a task tasks.md currently spells out explicitly.
run "plan_requires_non_empty_server_id" {
  command = plan

  variables {
    server_id = ""
  }

  expect_failures = [
    var.server_id,
  ]
}
