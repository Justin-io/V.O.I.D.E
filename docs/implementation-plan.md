# V.O.I.D.E. 2.0 Implementation Plan

| Milestone | Deliverable | Acceptance evidence | Status |
|---|---|---|---|
| 1. Asset model | Asset, sensor, event, failure taxonomy | contract unit tests | Implemented |
| 2. Simulator/replay | deterministic degradations, missingness, UTC replay | repeatable simulator + CSV replay tests | Implemented |
| 3. Baselines | proxy anomaly/risk/RUL and persistence comparator | benchmark output and metrics | Implemented; local run pending |
| 4. Leakage-safe evaluation | asset holdout and time ordering | asset disjointness tests | Implemented |
| 5. Uncertainty/evidence | heuristic RUL spread, event evidence | state and prediction assertions | Implemented |
| 6. Digital twin/scenarios | state projection and counterfactual scenario ranking | twin idempotency + ranking tests | Implemented |
| 7. Monitoring | simple mean-shift and ingestion quality primitives | monitor tests planned | Partial |
| 8. Reproducibility/deployment | data notes, CI, CLI/API, benchmark report | clean environment CI | In progress |

## Next work
1. Run `pytest -q`, formatting and static checks in a Python 3.10+ isolated environment; capture exact versions and output.
2. Add test coverage for drift monitor, API request validation and ingestion lag once ingestion timestamps exist.
3. Add explicit time-only backtesting within each held-out asset and lead-time / false-alarms-per-operating-hour metrics with event definitions.
4. Implement durable repository-backed twin state and bounded-lateness streaming ingestion.
5. Add real C-MAPSS and NASA battery adapter only after checking the exact dataset release terms, provenance and split protocol; do not assume a licence.
6. Train a proper survival/RUL model only when a documented failure/censoring target is available.
