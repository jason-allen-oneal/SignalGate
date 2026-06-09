# Runtime config drift

Runtime options now include emergency classifier controls and optional persistence:

- `classifier.incident_pin_tier`
- `classifier.incident_disable_classifier`
- `persistence.enabled`
- `persistence.sqlite_path`

The runtime uses the persistence block for circuit-breaker state. Budget persistence is available through the `BudgetManager` store path and can be enabled by wiring the same SQLite store into the manager.
