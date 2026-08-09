"""SERVER — our pi agent run under Polar via `import_path`.

Will hold the harness that launches our pinned pi inside the Polar-managed
sandbox, injects the per-episode retrieval cutoff, and keeps the tool
roster a pinned config input rather than baking it into argv (the G3 gap,
docs/CHARTER.md §7). Named `pi_harness` because "harness" alone already
means Polar's `BaseHarness` and pi itself (ADR-0001). Empty at CP-00 by
design; built at CP-06/CP-07.
"""
