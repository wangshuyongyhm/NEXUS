# Roadmap

## v1.1 (planned)
- [ ] PyPI publication (`pip install nexusos-xdr`)
- [ ] Wizard auto-creates starter-vault templates (task assets / decision log / session log)
- [ ] Client-side full-chain L3 verification for all five agents (hello-task end-to-end)

## v1.2 (exploring)
- [ ] Linux support (systemd unit + inotify instead of FSEvents/launchd)
- [ ] Internationalization of code comments
- [ ] MCP directory listing (mcp.directory / glama.ai)

## Done in v1.0
- [x] `.nexus` single-directory layout
- [x] Provisioning wizard (`nexus init` — Obsidian/PG three-choice, dedicated DB, minimal-privilege roles)
- [x] Update notifications (`nexus update`, 24h cached, zero telemetry)
- [x] Declarative gate scenes (init / dispatch / persist)
- [x] Five-agent onboarding guides (Claude Code / Codex / ZCode / Kimi / Cursor)
