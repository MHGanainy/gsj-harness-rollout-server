"""BOTH — trace validators.

The same validators run on the server (the receiver drops bad traces at
the source) and on the trainer (verify what arrived): token ids,
`loss_mask`, logprobs, sentinel guards, cutoff evidence. Same code on
both sides of the wire, so no trust is required across it (scope law 6).
Empty at CP-00 by design; built from CP-07, hardened at CP-10/CP-11.
"""
