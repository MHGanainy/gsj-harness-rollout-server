"""SERVER — callback endpoint + validation.

Will receive Polar's per-episode callback payload, run `checks.py` on the
trace at the source, and drop what fails before anything crosses the wire
(scope law 6: same checks on both sides, no trust required). Empty at
CP-00 by design; built at CP-08.
"""
