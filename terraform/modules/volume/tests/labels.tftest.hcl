# Tests for modules/volume's labeling behavior, derived from the
# add-prod-data-volume change's delta spec:
#   - specs/iac-safety-hardening/spec.md, "Consistent Resource Labeling"
#     (Scenario: Prod volume is labeled)
#
# Mirrors modules/server/main.tf's locals.labels pattern (merge of
# environment/managed_by with caller-supplied labels), per design.md's
# stated goal of matching modules/server's conventions closely.
#
# mock_provider avoids any real Hetzner API call -- see creation.tftest.hcl
# for the shared rationale.

mock_provider "hcloud" {}

variables {
  environment = "prod"
  name        = "main-data"
  size        = 10
  server_id   = "12345"
}

run "plan_applies_environment_and_managed_by_labels" {
  command = plan

  assert {
    condition     = hcloud_volume.this.labels["environment"] == var.environment
    error_message = "hcloud_volume.this did not carry the environment label"
  }

  assert {
    condition     = hcloud_volume.this.labels["managed_by"] == "terraform"
    error_message = "hcloud_volume.this did not carry the managed_by=terraform label"
  }
}

# DERIVED: the delta-spec scenario only requires environment/managed_by to
# be present; that caller-supplied labels merge in (and don't clobber the
# automatic ones) is inferred from modules/server's existing
# locals.labels = merge({...}, var.labels) pattern that this module is
# meant to mirror, not from the scenario text itself.
run "plan_merges_caller_supplied_labels_without_losing_automatic_ones" {
  command = plan

  variables {
    labels = {
      team = "platform"
    }
  }

  assert {
    condition     = hcloud_volume.this.labels["team"] == "platform"
    error_message = "hcloud_volume.this did not merge a caller-supplied label"
  }

  assert {
    condition     = hcloud_volume.this.labels["environment"] == var.environment
    error_message = "caller-supplied labels overrode the automatic environment label"
  }
}
