# modules/server's firewall is default-deny inbound (see main.tf's comment
# above hcloud_firewall.this): SSH is always allowed in, and HTTP/HTTPS are
# opt-in via a `dynamic "rule"` block that only fires when web_allowed_cidrs
# is non-empty. That conditional-creation path -- and the fact that no web
# rule leaks in when it shouldn't -- is exactly the kind of thing that's
# easy to break silently in a refactor and worth pinning down here.
#
# hcloud_firewall.this.rule is provider-typed as a set (unordered), so
# assertions below check for the presence of a matching rule via a `for`
# comprehension rather than indexing by position.
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

run "plan_ssh_rule_is_always_present" {
  command = plan

  assert {
    condition = anytrue([
      for r in hcloud_firewall.this.rule : (
        r.direction == "in" &&
        r.protocol == "tcp" &&
        r.port == "22" &&
        r.source_ips == toset(var.ssh_allowed_cidrs)
      )
    ])
    error_message = "hcloud_firewall.this did not carry an inbound TCP/22 rule scoped to ssh_allowed_cidrs"
  }
}

run "plan_no_web_rule_when_web_allowed_cidrs_is_empty" {
  command = plan

  assert {
    condition     = length(hcloud_firewall.this.rule) == 1
    error_message = "hcloud_firewall.this carried more than just the SSH rule with web_allowed_cidrs left empty -- a server with no web service should stay SSH-only"
  }
}

run "plan_http_and_https_rules_created_when_web_allowed_cidrs_is_set" {
  command = plan

  variables {
    web_allowed_cidrs = ["0.0.0.0/0"]
  }

  assert {
    condition     = length(hcloud_firewall.this.rule) == 3
    error_message = "hcloud_firewall.this did not carry exactly 3 rules (SSH + HTTP + HTTPS) once web_allowed_cidrs was set"
  }

  assert {
    condition = anytrue([
      for r in hcloud_firewall.this.rule : (
        r.direction == "in" &&
        r.protocol == "tcp" &&
        r.port == "80" &&
        r.source_ips == toset(var.web_allowed_cidrs)
      )
    ])
    error_message = "hcloud_firewall.this did not carry an inbound TCP/80 rule scoped to web_allowed_cidrs"
  }

  assert {
    condition = anytrue([
      for r in hcloud_firewall.this.rule : (
        r.direction == "in" &&
        r.protocol == "tcp" &&
        r.port == "443" &&
        r.source_ips == toset(var.web_allowed_cidrs)
      )
    ])
    error_message = "hcloud_firewall.this did not carry an inbound TCP/443 rule scoped to web_allowed_cidrs"
  }
}
