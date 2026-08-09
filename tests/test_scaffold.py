"""CP-00 scaffold test: the package imports and reports its version."""

import gsj_rollout


def test_version():
    assert gsj_rollout.__version__ == "0.1.0"
