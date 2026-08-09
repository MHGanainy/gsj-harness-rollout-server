"""gsj-harness-rollout-server — consumer surface (empty for now).

The package exports nothing beyond its version at CP-00. Runs on BOTH
sides: the trainer imports `client` and `checks` from here, the server
runs `pi_harness`, `receiver`, `config`, and `cli`. Logic arrives per the
plan in docs/CHARTER.md §6.
"""

__version__ = "0.1.0"
