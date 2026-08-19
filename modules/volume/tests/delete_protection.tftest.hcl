# Tests for modules/volume's delete_protection behavior, derived from the
# add-prod-data-volume change's delta spec:
#   - specs/iac-safety-hardening/spec.md, "Provider-Level Deletion
#     Protection" (Scenario: Prod volume is protected against console
#     deletion; Scenario: Shared module remains reusable by a future
#     non-prod environment)
#
# These scenarios' actual outcome -- Hetzner refusing a console/API
# deletion, or a future environment's `terraform destroy` succeeding -- is
# server-side provider behavior that cannot be observed via
# `terraform plan` (or via any test that never touches real
# infrastructure, per this pass's plan-only scope). What IS plan-testable,
# and is asserted below as the closest available proxy, is that
# delete_protection is exposed as a variable and passed through to the
# resource untouched in both directions -- i.e. the module does not
# hardcode it, which is the precondition both scenarios depend on. See
# test-manifest.md for this distinction.
#
# mock_provider avoids any real Hetzner API call -- see creation.tftest.hcl
# for the shared rationale.

mock_provider "hcloud" {}

variables {
  environment = "prod"
  name        = "production_data"
  size        = 10
  server_id   = "12345"
}

# DERIVED (tasks.md 1.2: "delete_protection (bool, default true)") -- not
# itself delta-spec scenario text, but the default value the module is
# specified to ship with.
run "plan_delete_protection_defaults_to_true" {
  command = plan

  assert {
    condition     = hcloud_volume.this.delete_protection == true
    error_message = "delete_protection did not default to true"
  }
}

run "plan_delete_protection_true_is_set_on_the_resource" {
  command = plan

  variables {
    delete_protection = true
  }

  assert {
    condition     = hcloud_volume.this.delete_protection == true
    error_message = "delete_protection = true was not reflected on hcloud_volume.this -- the volume would not carry Hetzner's server-side deletion lock"
  }
}

run "plan_delete_protection_is_parameterized_not_hardcoded" {
  command = plan

  variables {
    delete_protection = false
  }

  assert {
    condition     = hcloud_volume.this.delete_protection == false
    error_message = "delete_protection = false was not reflected on hcloud_volume.this -- the module may be hardcoding protection instead of exposing it as a variable, which would make it permanently undestroyable for a future non-prod consumer"
  }
}
