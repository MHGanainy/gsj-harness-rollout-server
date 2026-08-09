"""SERVER — one YAML.

Will load and validate the server's single YAML config: runtime selection
(Docker today, Apptainer kept free — scope law 5), Polar wiring, MCP
service endpoint, and the pinned tool roster (a hashed config field, never
argv — the G3 gap in docs/CHARTER.md §7). Empty at CP-00 by design; built
at CP-08.
"""
