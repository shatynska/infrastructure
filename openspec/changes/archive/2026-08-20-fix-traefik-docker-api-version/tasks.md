## 1. Implement the fix

- [x] 1.1 Change `image: traefik:v3.2` to `image: traefik:v3.7.10` in `platform/docker-compose.yml`.
- [x] 1.2 Run `cp platform/.env.example platform/.env && docker compose -f platform/docker-compose.yml config; rm platform/.env` locally to confirm the file still validates, mirroring `pr-validation.yml`'s validation step. (Local Docker unavailable in the working environment; covered instead by `pr-validation.yml`'s real run against this PR — see 2.1.)

## 2. Ship through the gated pipeline

- [x] 2.1 Open a PR with the change; confirm `pr-validation.yml` passes. PR: https://github.com/shatynska/infrastructure/pull/38 — `validate` check passed.
- [x] 2.2 On merge to `main`, confirm `platform-deploy.yml`'s `diff` job posts the expected one-line image-tag diff to the job summary. Run https://github.com/shatynska/infrastructure/actions/runs/32355056250 — both `diff` and `deploy` jobs succeeded.
- [x] 2.3 Approve the gated `deploy` job. Approved by the user; deploy completed 2026-08-20T09:40:47Z.

## 3. Verify in production

- [x] 3.1 `docker logs platform-traefik-1` on the host shows no further `Provider error` entries after the deploy. Confirmed: `platform-traefik-1` running `traefik:v3.7.10`, zero provider errors since restart (vs. continuous failures on `v3.2`).
- [x] 3.2 Redeploy the throwaway `whoami` test container (or a new one) labeled for `test.shatynska.com`, and confirm `https://test.shatynska.com` returns whoami's response with a valid Let's Encrypt certificate (not Traefik's default self-signed one). Confirmed: HTTP 200, whoami response body, certificate issued by Let's Encrypt for `CN = test.shatynska.com`.
- [x] 3.3 Tear down the throwaway test container and its directory on the host. Done — `docker compose down` and `~/test-service` removed from the host.
