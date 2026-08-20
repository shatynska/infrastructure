## 1. Implement the fix

- [ ] 1.1 Change `image: traefik:v3.2` to `image: traefik:v3.7.10` in `platform/docker-compose.yml`.
- [ ] 1.2 Run `cp platform/.env.example platform/.env && docker compose -f platform/docker-compose.yml config; rm platform/.env` locally to confirm the file still validates, mirroring `pr-validation.yml`'s validation step.

## 2. Ship through the gated pipeline

- [ ] 2.1 Open a PR with the change; confirm `pr-validation.yml` passes.
- [ ] 2.2 On merge to `main`, confirm `platform-deploy.yml`'s `diff` job posts the expected one-line image-tag diff to the job summary.
- [ ] 2.3 Approve the gated `deploy` job.

## 3. Verify in production

- [ ] 3.1 `docker logs platform-traefik-1` on the host shows no further `Provider error` entries after the deploy.
- [ ] 3.2 Redeploy the throwaway `whoami` test container (or a new one) labeled for `test.shatynska.com`, and confirm `https://test.shatynska.com` returns whoami's response with a valid Let's Encrypt certificate (not Traefik's default self-signed one).
- [ ] 3.3 Tear down the throwaway test container and its directory on the host.
