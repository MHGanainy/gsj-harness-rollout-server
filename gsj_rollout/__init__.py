"""gsj-harness-rollout-server — the consumer surface (CP-08, ADR-0008 §7).

The trainer imports from here: `RolloutClient`/`Trace` (submit + collect),
`checks` (the same validators the receiver ran — law 6), `load_config`/
`RunConfig` (the one YAML). Deliberately not exported: `pi_harness` and
`builder` (Polar loads them by import path and they import `polar`, which
only exists in Polar's venv) and `receiver`/`cli` (server-internal,
reached via the `gsj-rollout` console script). Importing `gsj_rollout`
never imports `polar`.
"""

from . import checks
from .client import RolloutClient, Trace
from .config import RunConfig, load_config

__version__ = "0.1.1"

__all__ = ["RolloutClient", "Trace", "checks", "load_config", "RunConfig", "__version__"]
