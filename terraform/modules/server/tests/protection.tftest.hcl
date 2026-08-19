# modules/server couples rebuild_protection to the same delete_protection
# variable rather than exposing it separately (see main.tf:53-54). That
# coupling is a deliberate but non-obvious design choice -- worth pinning
# down explicitly so a future edit doesn't accidentally decouple or invert
# it.
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

run "plan_delete_and_rebuild_protection_default_to_true" {
  command = plan

  assert {
    condition     = hcloud_server.this.delete_protection == true
    error_message = "delete_protection did not default to true"
  }

  assert {
    condition     = hcloud_server.this.rebuild_protection == true
    error_message = "rebuild_protection did not default to true alongside delete_protection"
  }
}

run "plan_delete_protection_false_also_disables_rebuild_protection" {
  command = plan

  variables {
    delete_protection = false
  }

  assert {
    condition     = hcloud_server.this.delete_protection == false
    error_message = "delete_protection = false was not reflected on hcloud_server.this"
  }

  assert {
    condition     = hcloud_server.this.rebuild_protection == false
    error_message = "rebuild_protection did not follow delete_protection = false -- the coupling in main.tf between the two appears to have broken"
  }
}
