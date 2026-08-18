"""CP-00 scaffold test: the package imports and reports its version."""

import gsj_rollout


def test_version():
    assert gsj_rollout.__version__ == "0.1.2"


def test_consumer_surface():
    # ADR-0008 §7: what a trainer imports — and nothing pulls in `polar`.
    import sys

    from gsj_rollout import RolloutClient, RunConfig, Trace, checks, load_config  # noqa: F401

    assert callable(checks.validate_session_result)
    assert "polar" not in sys.modules
