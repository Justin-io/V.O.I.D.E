# V.O.I.D.E. — Autonomous Telemetry Intelligence & Industrial Digital Twin

V.O.I.D.E. is an open-source industrial telemetry workbench. This repository preserves the original V.O.I.D.E. 1.x Python + Flutter system and adds an isolated **V.O.I.D.E. 2.0** digital-twin and predictive-intelligence MVP under `voide2/`.

## V.O.I.D.E. 2.0 capability slice

- Explicit asset/sensor contracts with engineering units and data-quality bounds.
- UTC event-time CSV ingestion, schema validation, deterministic replay and missing-value tracking.
- Reproducible synthetic chiller telemetry with degradation trajectories, noise and missingness; ground truth is a separate file.
- Per-asset twin state with idempotent event application, evidence, health status, risk score and heuristic RUL.
- Statistical risk/RUL baseline plus persistence comparator.
- Asset-wise held-out evaluation split; chronological tail holdout for remaining assets.
- Counterfactual maintenance scenario ranking with explicit assumptions.
- FastAPI surface, CLI, drift/ingestion monitors and machine-readable benchmark exports.

**Scientific boundary:** RUL is trend extrapolation on a proxy, failure risk is an uncalibrated score, and uncertainty is heuristic. Synthetic degradation-phase labels are not observed failures. No real plant measurements, predictive-maintenance performance claims, safety certification, or actuation are represented.

## Quickstart

Python 3.10+; CPU-first:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m voide2 demo --out artifacts/demo
```

The demo writes:
- `telemetry.csv`: synthetic sensor observations.
- `ground_truth.csv`: separate health/degradation labels.
- `benchmark/benchmark.json`: metrics, split, environment and state.
- `benchmark/benchmark.md`: short report.
- `benchmark/predictions.csv`: per-event estimates and evidence.

Other commands:

```bash
python -m voide2 simulate --out artifacts/demo --assets 4 --hours 240 --seed 20261112
python -m voide2 replay artifacts/demo/telemetry.csv --out artifacts/replay
```

CSV requires `event_time,asset_id,event_id` and declared sensor columns. Event time must be ISO-8601 with timezone. The provided replay command assumes the reference chiller schema; custom assets must define their own `AssetSpec`.

## API

```bash
uvicorn voide2.api:app --host 127.0.0.1 --port 8767
```

- `GET /health`
- `POST /replay` with `{"csv_path":"artifacts/demo/telemetry.csv"}`
- `POST /load-twin` with a CSV path
- `GET /fleet`
- `POST /scenarios` with asset ID and scenario assumptions

The API accepts host filesystem paths. Keep it bound to localhost or behind a trusted boundary. It is not a hardened multi-tenant service.

## Quality gates

```bash
python -m compileall -q voide2
python -m pytest -q tests/voide2
ruff check voide2 tests/voide2
python -m voide2 demo --out artifacts/demo
```

GitHub Actions runs syntax validation, the V.O.I.D.E. 2.0 test suite and reproducible demo export.

## Architecture and governance

- [Architecture](docs/architecture.md)
- [Implementation plan](docs/implementation-plan.md)
- [Assumptions](docs/assumptions.md)
- [Risk register](docs/risk-register.md)
- [Validation log](docs/validation-log.md)
- [Original 1.x architecture](docs/architecture/ARCHITECTURE.md)

V.O.I.D.E. 2.0 deliberately starts with a simulator and CSV adapter. PostgreSQL/TimescaleDB, MLflow, Prometheus, trained survival/RUL models, bounded-lateness streaming and authenticated production ingestion are future milestones, not claimed features.

## Public dataset provenance

No NASA dataset is included by default. Before integrating C-MAPSS, NASA battery prognostics or another public dataset, record the exact release, URL, provenance, licence/terms, redistribution limits, target definitions, asset identifiers, censoring protocol and split protocol. Do not infer a licence from a portal or paper citation.

## Existing 1.x system

The original Python agent, data engine, SQLite/WAL store, native host services and Flutter app are preserved. V.O.I.D.E. 2.0 is additive: it does not migrate 1.x data or claim the desktop UI has been upgraded to show twin state.

## Licence

MIT. See [LICENSE](LICENSE).
