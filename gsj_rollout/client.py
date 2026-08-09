"""TRAINER — submit + collect.

The trainer-side surface: submit tasks `(case, timestep, prompt)` to the
rollout server and collect validated traces back. Installs light — the
core distribution carries only `pydantic`, `httpx`, `pyyaml` (ADR-0001).
Empty at CP-00 by design; built at CP-08.
"""
