# Contributing to V.O.I.D.E.

Thank you for your interest in contributing to **V.O.I.D.E.** (**Autonomous Multi-Layer Telemetry Anomaly Detection & Industrial Equipment Health Monitoring System**)! We welcome community contributions, bug fixes, algorithmic enhancements, and documentation improvements.

---

## Development Principles

1. **Zero Unnecessary Dependencies**: Keep the core agent runtime lightweight and hermetic. Leverage Python standard library modules (`urllib.request`, `asyncio`, `subprocess`, `sqlite3`) whenever possible.
2. **Deterministic & Hermetic Testing**: Tests must never rely on live external web servers or require proprietary API keys to pass. Always provide mock responses or deterministic local testing modes.
3. **Zero-Trust Security & Path Sandboxing**: Every filesystem access must enforce path traversal validation (`os.path.commonpath([workspace_root, target]) == workspace_root`). Secrets must be masked before emission to IPC or logging.
4. **Clean Code & Strict Typing**: Follow PEP 8, enforce type annotations, and maintain clean separation of concerns across adapters, runtime engines, and storage.

---

## Setting Up Your Development Environment

```bash
# 1. Clone repository
git clone https://github.com/your-username/V.O.I.D.E.git
cd V.O.I.D.E

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

---

## Running Test Suites

Before submitting pull requests, ensure all unit and integration tests pass:

```bash
# Run complete test suite
pytest -v

# Run Flutter desktop analyzer (if modifying Dart code)
cd apps/voide_desktop && flutter analyze
```

---

## Code Structure Overview

```
V.O.I.D.E/
├── agent/                  # Python Agent Runtime
│   ├── adapters/           # LLM Providers (OpenAICompatible, Deterministic)
│   ├── data_engine/        # Telemetry ingestion, profiling & baseline models
│   ├── policy/             # Security policy mediation & risk tiers
│   ├── runtime/            # Core ReAct loop, APIStreamer, IPC WebSocket server
│   ├── storage/            # SQLite schema and state store
│   └── tools/              # Typed tool definitions and broker
├── apps/
│   └── voide_desktop/      # Flutter Linux Desktop Client
├── browser/
│   └── chromium_shell/     # Generic CDP controller & DOM intelligence scripts
├── docs/                   # Architectural & Protocol documentation
└── tests/                  # Hermetic unit & integration test suites
```

---

## Pull Request Guidelines

- Branch names should be descriptive: `feat/ollama-streaming`, `fix/pty-eof-handling`, `docs/readme-diagram`.
- Accompany new features with targeted unit tests in `tests/unit/`.
- Ensure no hardcoded personal filesystem paths or unmasked secrets are committed.
