# Phase 6B final review remediation report

## Status

The Phase 6B final-review follow-ups are implemented through `97b7874` within
the Phase 6B write set. The remaining Important content-equivalence finding now
has automated regression coverage. No Phase 6C file, B2B1 WIP,
governance/migration file, shared Dockerfile/README/settings file, or
user-protected file was modified or staged.

The code is ready to commit, but production alert deployment is intentionally
release-gated: the canonical GitHub blob and raw runbook URLs currently return
HTTP 404 because this branch is not yet published to `main`. The runbook now
requires merge/publication before production-mode preflight and alert rollout.

## Final-review remediation

### 1. Monitoring-role convergence

`deploy/observability/provision-roles.sh` now converges existing roles instead
of assuming fresh roles:

- dynamically enumerates `pg_auth_members` and revokes every inbound
  membership from both exporter identities;
- restores only ordinary, non-admin `pg_monitor` membership to the PostgreSQL
  exporter, while the queue exporter finishes with zero memberships;
- resets role-local configuration and explicitly converges login, inheritance,
  superuser, create-role/database, replication, bypass-RLS, connection-limit,
  and password-validity attributes;
- revokes direct database, schema, table/view, sequence, and function grants
  across existing schemas, then restores only required `CONNECT`, queue-view
  access, and `pg_monitor`;
- uses quiet psql execution and fixed success output so successful provisioning
  exposes neither exporter identities nor passwords.

The disposable PostgreSQL test deliberately creates a malicious extra role
with `background_jobs` SELECT, grants both exporters that role with admin
option, grants postgres-exporter `pg_monitor` with admin option, adds direct
table access, and poisons role attributes/config. After two provisioning runs,
it proves the queue identity has no memberships and cannot read base tables;
postgres-exporter has exactly `pg_monitor` without admin option and cannot read
the queue view or base tables; direct grants and attributes match the contract.

### 2. Host filesystem capacity with bounded privileges

Node-exporter now uses the official rootfs pattern with exactly one host-root
bind mount at `/host/root`, read-only with `rslave` propagation, plus
`--path.rootfs=/host/root` and host PID visibility. The service remains private
and adds `read_only: true`, `cap_drop: [ALL]`, and
`no-new-privileges:true`. cAdvisor, privileged mode, Docker socket,
`/var/run`, and Docker data mounts remain forbidden.

Topology tests prove no other service receives a host-root mount and reject a
writable, propagation-free, or differently targeted root mapping. The runtime
gate proves a matching `node_filesystem_avail_bytes` /
`node_filesystem_size_bytes` pair survives the HostStorageLow
`fstype!~"tmpfs|overlay"` filter.

Docker Desktop cannot start the production `rslave` mount because its Linux VM
root is not a shared/slave mount. The runtime test detects only that exact
Docker Desktop limitation and uses an otherwise identically hardened,
read-only diagnostic mount to prove the Linux VM filesystem topology is
nonempty. This does not replace the documented production Linux host gate,
which must exercise the exact Compose service and observe real host filesystems.

### 3. Published runbook availability gate

The ordinary preflight remains offline for development/static CI. With
`OBSERVABILITY_PREFLIGHT_MODE=production`, it now:

1. runs the existing production preflight and fixed three-file Compose check;
2. requires `curl` and verifies both the canonical GitHub blob URL and raw URL;
3. requires every alert URL to use the canonical base;
4. checks every alert fragment against both local and published runbook
   headings; and
5. normalizes only CRLF/LF line endings and uses `cmp -s` to require the full
   published body to equal the current local runbook.

Tests use a local curl shim, so offline CI never depends on external network.
They prove production mode checks both URLs, accepts aligned remote content,
and rejects a published runbook missing a local alert anchor. The runbook makes
publication to `main` a required predecessor of production alert deployment;
the current real 404 is recorded as that expected release-order block, not as
evidence of online availability.

### 4. Full published-content equivalence

The production gate no longer treats matching headings as sufficient. It uses
three `mktemp` files for the downloaded raw runbook and the local/remote
line-ending-normalized copies, installs cleanup traps before allocation, and
removes every temporary file on success, HTTP failure, content mismatch, or
signal. It never prints either runbook body.

Regression tests prove that identical complete content passes, while a remote
file containing every matching heading but no body and a remote file with one
stale body sentence both fail. A simulated HTTP 404 remains fail-closed, and
the development-mode curl shim proves offline preflight makes no network call.

## TDD evidence

RED against the `586639f` behavior:

- production preflight made no canonical URL requests and accepted incomplete
  published content;
- topology found zero approved host-root mappings, so the host-storage alert
  lacked a reliable filesystem source;
- malicious-role real-PG testing exposed exporter identities in psql warnings
  and retained unexpected membership/admin-option paths.

GREEN after the scoped fixes:

- focused real disposable PostgreSQL exporter/role suite: `8 passed`;
- Phase 6A production topology + Phase 6B topology/preflight: `19 passed`;
- node-exporter static boundary and Docker Desktop VM runtime subset:
  `2 passed`;
- preflight offline/production simulation and release-order documentation:
  `6 passed` for the final content-equivalence focused suite;
- final preflight plus static topology rerun: `11 passed, 1 deselected`; the
  node runtime gate was intentionally excluded per the final-review request;
- ordinary installed preflight: success;
- real production-mode preflight before publication: expected fail-closed,
  curl exit 22 / HTTP 404 for both canonical URLs.

## Remaining release gates and deferred work

- Merge the exact alert/runbook commit to `main`, then rerun
  `OBSERVABILITY_PREFLIGHT_MODE=production` and require a clean pass before
  deploying alert rules.
- Repeat the node-exporter runtime gate on the production Linux host; Docker
  Desktop evidence covers only its Linux VM.
- Backup freshness remains disabled until Phase 6C supplies restore-aware
  evidence and tests.
- Container-level metrics remain deferred; no cAdvisor or container-engine
  socket access is introduced.
- Alertmanager still uses the null canary receiver pending approved production
  routing and secret integration.

## Commit

Base commit: `97b7874 fix(observability): close final review gaps`.
Intended follow-up subject:
`fix(observability): verify published runbook content`.
The immutable follow-up hash is reported in the final handoff because a commit
cannot contain its own hash.
