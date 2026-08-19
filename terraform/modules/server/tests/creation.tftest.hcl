# Core creation behavior of modules/server: the attributes it sets
# directly from its own input variables, and the wiring between the two
# resources it creates (hcloud_server attached to hcloud_firewall).
#
# mock_provider replaces the real hcloud provider so no Hetzner API call or
# credential is required to run these tests (command = plan only, no real
# infrastructure is ever touched).

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

run "plan_creates_server_with_declared_configuration" {
  command = plan

  assert {
    condition     = hcloud_server.this.name == var.name
    error_message = "hcloud_server.this.name did not match the declared server name"
  }

  assert {
    condition     = hcloud_server.this.server_type == var.server_type
    error_message = "hcloud_server.this.server_type did not match the declared server type"
  }

  assert {
    condition     = hcloud_server.this.image == var.image
    error_message = "hcloud_server.this.image did not match the declared image"
  }

  assert {
    condition     = hcloud_server.this.location == var.location
    error_message = "hcloud_server.this.location did not match the declared location"
  }
}

run "plan_attaches_the_given_ssh_key_and_no_other" {
  command = plan

  assert {
    condition     = length(hcloud_server.this.ssh_keys) == 1
    error_message = "hcloud_server.this.ssh_keys did not contain exactly one key -- a server created with more than the caller's key, or none, changes who can authenticate to it"
  }

  assert {
    condition     = hcloud_server.this.ssh_keys[0] == var.ssh_key_id
    error_message = "hcloud_server.this.ssh_keys did not contain the declared ssh_key_id"
  }
}

run "plan_attaches_the_modules_own_firewall_and_no_other" {
  command = plan

  # hcloud_firewall.this.id is provider-computed and stays unknown at plan
  # time, so the exact cross-resource reference (main.tf:49,
  # `firewall_ids = [hcloud_firewall.this.id]`) can't be asserted on here --
  # only that the server ends up attached to exactly one firewall. Compare
  # modules/volume/tests/creation.tftest.hcl's own note on why
  # provider-computed-only attributes aren't asserted on under plan.
  assert {
    condition     = length(hcloud_server.this.firewall_ids) == 1
    error_message = "hcloud_server.this.firewall_ids did not contain exactly one firewall -- the server would be reachable without this module's declared rules governing it, or attached to an unexpected extra firewall"
  }
}

run "plan_backups_default_to_true" {
  command = plan

  assert {
    condition     = hcloud_server.this.backups == true
    error_message = "backups did not default to true"
  }
}

run "plan_backups_can_be_disabled" {
  command = plan

  variables {
    backups = false
  }

  assert {
    condition     = hcloud_server.this.backups == false
    error_message = "backups = false was not reflected on hcloud_server.this -- the module may be hardcoding backups instead of exposing it as a variable"
  }
}
