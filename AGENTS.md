# BeyondCandidate Enterprise Agent Entry

Before working in this repository, read:

1. `.agents/README.md`
2. `.agents/repository-map.md`
3. `.agents/development.md`
4. `.agents/deployment.md`
5. `.agents/agent-workflow.md`

This is the private enterprise deployment repository. Product code belongs in the public repository and is synchronized here through the `product` submodule.

The current checkout and the nearest repository documentation are authoritative. Preserve unrelated user changes and historical worktrees. Never copy enterprise domains, IP addresses, accounts, certificates, API keys, real resumes, interview feedback, or private deployment configuration into the public repository.

For an explicit production deployment request, do not improvise SSH, Docker Compose, TLS, or Nginx commands. Read `.agents/deployment.md` and run the root `部署到生产.ps1` entrypoint. It handles first-machine detection, release scope, migrations, route safety checks, health verification, and rollback.
