# modules/server's variable validation blocks are its only defense against
# a server being created SSH-less-secured or with no source restriction at
# all -- see variables.tf's ssh_allowed_cidrs description. These tests pin
# each validation's rejection behavior down individually so a future edit
# to the condition can't silently loosen it.
#
# mock_provider avoids any real Hetzner API call -- see creation.tftest.hcl
# for the shared rationale. expect_failures runs never reach a resource
# call regardless, since validation fails before the plan is built.

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

run "plan_rejects_empty_environment" {
  command = plan

  variables {
    environment = ""
  }

  expect_failures = [
    var.environment,
  ]
}

run "plan_rejects_blank_environment" {
  command = plan

  variables {
    environment = "   "
  }

  expect_failures = [
    var.environment,
  ]
}

run "plan_rejects_empty_ssh_allowed_cidrs" {
  command = plan

  variables {
    ssh_allowed_cidrs = []
  }

  expect_failures = [
    var.ssh_allowed_cidrs,
  ]
}

run "plan_rejects_ssh_open_to_all_ipv4" {
  command = plan

  variables {
    ssh_allowed_cidrs = ["0.0.0.0/0"]
  }

  expect_failures = [
    var.ssh_allowed_cidrs,
  ]
}

run "plan_rejects_ssh_open_to_all_ipv6" {
  command = plan

  variables {
    ssh_allowed_cidrs = ["::/0"]
  }

  expect_failures = [
    var.ssh_allowed_cidrs,
  ]
}

run "plan_rejects_ssh_open_to_all_ipv4_even_alongside_a_real_cidr" {
  command = plan

  variables {
    ssh_allowed_cidrs = ["203.0.113.0/24", "0.0.0.0/0"]
  }

  expect_failures = [
    var.ssh_allowed_cidrs,
  ]
}
