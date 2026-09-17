## ADDED Requirements

### Requirement: Deploy Job Reaches the Host Over a Private Tailnet
The deploy job SHALL join the same private tailnet the host is a member of (via an ephemeral, tagged node authenticated by a Tailscale OAuth client) before attempting any SSH connection to the host, and SHALL connect to the host's tailnet address rather than a publicly-routable one reachable outside the tailnet.

#### Scenario: Deploy job joins the tailnet before SSH
- **WHEN** the deploy job runs
- **THEN** it SHALL establish tailnet connectivity before its first SSH attempt, and that attempt SHALL succeed only if the host is reachable over the tailnet

#### Scenario: Tailnet join credential is confined to the gated job
- **WHEN** the deploy workflow run is pending `production` Environment approval
- **THEN** the Tailscale OAuth client secret SHALL NOT be readable by any job that has not passed that environment's approval gate, consistent with the existing Deploy Credential Confined to the Gated Job requirement
