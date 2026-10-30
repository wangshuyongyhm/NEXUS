# Contributing

Thanks for your interest in NEXUS.

## Quick start for contributors

```bash
git clone https://github.com/wangshuyongyhm/NEXUS.git && cd NEXUS
pip install -e packages/nexusos-common
pip install pytest
pytest packages/nexusos-common -q    # zero-dep suite should be green
```

## How to contribute

1. Fork & create a feature branch
2. Make your changes (see `starter-vault/task-spec.md` for the task format we use internally)
3. Ensure the core suite passes: `pytest packages/nexusos-common -q`
4. Open a Pull Request with a clear description

## Reporting issues

Use the issue templates (bug / feature). For questions, use [Discussions](https://github.com/wangshuyongyhm/NEXUS/discussions).
