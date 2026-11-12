# V.O.I.D.E. 2.0 Risk Register

| Risk | Impact | Mitigation | State |
|---|---|---|---|
| Synthetic degradation confused with real failures | Invalid reliability claims | separate ground_truth.csv; mark synthetic everywhere; explicit benchmark warning | Mitigated in design |
| RUL heuristic misused as actual remaining life | Unsafe maintenance decisions | expose uncertainty and model name; label as baseline; no actuation | Open / high |
| Asset leakage inflates evaluation | False generalization claims | asset-wise holdout; assert disjoint asset sets | Addressed in code; test execution pending |
| Late events regress twin state | Incorrect asset snapshot | deterministic finite replay; reject late state mutations | Addressed in code |
| CSV units / schema mismatch | Misleading predictions | explicit sensor contracts and strict unknown-column rejection | Addressed in code |
| Ingestion lag unavailable | Observability gap | report null until ingestion timestamp provided | Open |
| Drift thresholds arbitrary | Alert fatigue | expose reference distribution and threshold; require calibration | Open |
| No production persistence | State lost on process restart | document in-memory MVP; add durable store in next milestone | Open |
| Public dataset licence / split protocol unclear | Compliance and leakage risk | do not bundle until exact version, provenance, terms and protocol verified | Open |
| Current workspace not attached to this execution | Cannot run terminal / inspect host / GUI | use GitHub file API; report local test gates as unverified | Blocker |
| API file path access | arbitrary host file access if exposed beyond localhost | require trusted deployment boundary; add upload/storage abstraction before public deployment | Open / high |
| Failure risk score not calibrated | misinterpreted probabilities | name as score; evaluate Brier / calibration on real failure labels | Open |
