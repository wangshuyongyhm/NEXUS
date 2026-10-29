# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security reports. Send a GitHub
private message to [@wangshuyongyhm](https://github.com/wangshuyongyhm)
(or use GitHub's private vulnerability reporting on this repository).

Include: affected version/commit, a minimal reproduction, and whether the
issue is exploitable from a fresh install or only in the author's own
deployment. You will get an acknowledgment within 3 days.

## Scope

- In scope: the dispatch bus, knowledge base, gate engine, credential
  handling (HMAC-signed, TTL-bound, task-bound), and the installer/wizard.
- Notes: NEXUS services bind to 127.0.0.1 by design; do not expose them to
  untrusted networks. Agent drivers are not bundled — vulnerabilities in the
  agents themselves belong to their vendors.

Thank you for helping keep NEXUS and its users safe.
