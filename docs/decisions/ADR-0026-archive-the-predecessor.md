# ADR-0026 — archive the predecessor

Date: 2026-08-25 (CP-45). Status: accepted.

## Context

`gsj-envloader` @ v0.8.0 has been "alive, frozen, not retired" since
this repo's CP-00: law 3 (charter §8 rule 3) forbade every checkpoint
from writing to it, the VERDICT's provisional adopt required it stay
frozen-alive as the fallback, and both golden references
(`docs/golden/mac/`, `docs/golden/h200/`) were collected *through* it —
A-1's resolution compares against those traces. The fallback condition
was a term of the *provisional* adopt, and the verdict converted to
ADOPT on 2026-08-11 (CP-17: converting condition 2, the slime loop;
condition 1, the H200 golden pair, the same day), with a second trainer
(verl, CP-20/CP-21, 2026-08-12) widening the evidence afterward — so
the term expired then, and no entry said so. Meanwhile the fallback
framing kept a public repo looking maintained that no one maintains.

## Decision

Archive, not delete — three decisions:

1. **The fallback role is retired.** The frozen-alive condition expired
   at the conversion (2026-08-11, CP-17); CP-45 records the expiry in
   the VERDICT and retires the role. Falling back to the predecessor is
   no longer a standing plan of record.
2. **The evidence role continues.** The predecessor is the collecting
   stack for both goldens; the citations are content-addressed (wheel
   sha256 `a6921de6…`; checkout `4037bc2` — the v0.8.0 tag commit) and
   need exactly what archiving preserves: read access to v0.8.0.
   Archiving *strengthens* them — the platform now enforces the freeze.
3. **Law 3 becomes historical.** It bound CP-00–CP-44 and did its job:
   the predecessor reached the archive byte-untouched. CP-45 makes the
   single permitted write — a README archive header naming what the
   repo was, what superseded it, and the one live reason it must remain
   readable — pushes it, and sets the GitHub repo to archived. The
   protection is archival rather than operational from here.

The verification predicate changes once, deliberately: "HEAD ==
v0.8.0" becomes "`git diff v0.8.0 --stat` touches only `README.md`"
(the tag is the archive commit's parent).

## Consequence

The predecessor's GitHub repo is read-only; its tags, history, and
release assets stay fetchable, so every content-addressed citation in
the manifests, the charter, and the wishlist stays checkable. Every
statement site of law 3 (charter preamble, charter §8 rule 3,
CLAUDE.md scope law 3, README.md) is amended to historical in the same
commit — CLAUDE.md and README.md sit outside the CP-45 freeze-lift and
are amended anyway as declared scope_drift, §8 rule 8's CP-33/CP-39
history (a rule amended in one statement site and left stale in
another) being the recorded cost of the alternative. The frozen
`gsj-envloader-examples` repo still frames the predecessor as a going
concern and cannot be annotated (consumer-repo edits out of scope);
readers cross a "Public archive" banner mid-narrative — accepted. Any
future write to the predecessor (none is anticipated) would require
un-archiving on GitHub plus a new ADR superseding this one.
