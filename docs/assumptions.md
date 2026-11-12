# V.O.I.D.E. 2.0 Assumptions and Decisions

- Initial reference asset is a synthetic chiller, preserving the repository's chiller telemetry heritage.
- Sensor names / units: load_pct (%), flow_lps (L/s), power_kw (kW), bearing_temp_c (degC), vibration_mm_s (mm/s), ambient_temp_c (degC). Contract ranges are permissive data-quality checks, not operating envelopes.
- Simulator timestamps begin at 2026-01-01 UTC; interval defaults to 10 minutes. Seed defaults to 20261112.
- Simulator failure mode categories are bearing_wear, thermal_overload and efficiency_loss. The ground-truth file records degradation phase, health proxy and failure mode separately from sensor telemetry. Degradation-phase labels are not observed physical failure events.
- CSV must contain event_time (ISO 8601 with timezone), asset_id and event_id, plus declared sensor columns. Unknown columns are rejected to catch schema drift.
- Asset-wise holdout is primary for generalization. Held-out assets are never present in training. With more than two assets, the non-held-out assets also receive a chronological tail test segment.
- No event ingestion timestamp exists in this first CSV contract; ingestion lag remains null rather than fabricated.
- RUL is a transparent trend baseline with heuristic uncertainty. It must not be used for maintenance dispatch without validation on representative assets and failure/censoring histories.
- Scenario effect sizes, costs and downtime are supplied assumptions. The engine ranks scenarios; it does not execute maintenance or controls.
- PostgreSQL/TimescaleDB is deferred until the event and twin contracts are stable.
- NASA C-MAPSS / battery datasets are not bundled and no licence assertion is made. Their specific download version and terms must be recorded before integration.
