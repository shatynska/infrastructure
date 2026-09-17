config {
  format = "compact"
}

# Bundled terraform-language ruleset only. There is no Hetzner/hcloud
# tflint ruleset to enable — see design.md decision 5.
plugin "terraform" {
  enabled = true
  preset  = "recommended"
}
