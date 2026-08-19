# modules/server's locals.labels merge (environment + managed_by +
# caller-supplied labels) is applied to both resources it creates. Mirrors
# modules/volume/tests/labels.tftest.hcl's coverage of the same pattern.
#
# mock_provider avoids any real Hetzner API call -- see creation.tftest.hcl
# for the shared rationale.

mock_provider "hcloud" {}

variables {
  environment       = "prod"
  name              = "web-01"
  server_type       = "cx22"
  image             = "ubuntu-24.04"
  location          = "fsn1"
  ssh_key_id        = "12345"
  ssh_allowed_cidrs = ["203.0.113.0/24"]
}

run "plan_applies_environment_and_managed_by_labels_to_both_resources" {
  command = plan

  assert {
    condition     = hcloud_server.this.labels["environment"] == var.environment
    error_message = "hcloud_server.this did not carry the environment label"
  }

  assert {
    condition     = hcloud_server.this.labels["managed_by"] == "terraform"
    error_message = "hcloud_server.this did not carry the managed_by=terraform label"
  }

  assert {
    condition     = hcloud_firewall.this.labels["environment"] == var.environment
    error_message = "hcloud_firewall.this did not carry the environment label"
  }

  assert {
    condition     = hcloud_firewall.this.labels["managed_by"] == "terraform"
    error_message = "hcloud_firewall.this did not carry the managed_by=terraform label"
  }
}

run "plan_merges_caller_supplied_labels_without_losing_automatic_ones" {
  command = plan

  variables {
    labels = {
      team = "platform"
    }
  }

  assert {
    condition     = hcloud_server.this.labels["team"] == "platform"
    error_message = "hcloud_server.this did not merge a caller-supplied label"
  }

  assert {
    condition     = hcloud_server.this.labels["environment"] == var.environment
    error_message = "caller-supplied labels overrode the automatic environment label on hcloud_server.this"
  }

  assert {
    condition     = hcloud_firewall.this.labels["team"] == "platform"
    error_message = "hcloud_firewall.this did not merge a caller-supplied label"
  }
}
