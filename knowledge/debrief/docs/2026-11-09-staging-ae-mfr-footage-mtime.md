---
incident: 2026-11-09-staging-ae-mfr-footage-mtime
date: 2026-11-09
store: staging
session_id: codex 01a1be3c-819e-7472-aa1a-62ef63476b90
---

Closeout: diagnosis complete; staging workaround validated; implementation testing and production rollout deferred. Evidence IDs refer to the [incident record](../../incidents/2026-11-09-staging-ae-mfr-footage-mtime.md).

## Time sinks

- Renderer access/context setup | not separately measured | a staging PC access preflight and documented interactive AE runner would remove repeated environment checks.
- Broad effect/decoder/media theories | not separately measured | inspect native dumps and compare native-resaved metadata earlier, then use strict single-field experiments.

## Asked the user, should have known

- The supported toolkit documented production PC access only; direct staging WinRM required explicit fallback authorization. A missing local credential file then required user provisioning. Neither should be bypassed, but both can be detected before a render attempt.

## Wrong assumptions

1. Initially overgeneralized a successful full import-record repair as GUID-plus-timestamp only. A complete byte audit found additional field changes on session media; the final strict split corrected that claim (E8–E10).
2. An XML attribute-only inspection missed the GPU setting stored as a GUID in text. Native reopen verification corrected the interpretation (E5).
3. Raw dump addresses and nearest-export names were initially suggestive rather than a reliable call stack. Unwinding with matching PE modules gave stronger evidence; private function identity and the exact race remain unproven (E12).

## Toolkit friction

- [high] `docs/diagnose_toolkit.md`: staging renderer access and interactive execution were not covered. Proposal: add a staging PC discovery/access preflight and a guarded diagnostic runner that matches the worker's desktop context.
- [high] Native render evidence: watchdog messages obscured crashes, and `aerender` could return zero after a native connection error. Proposal: persist per-run stdout/stderr, exact arguments, output validation, and newly created native dumps together.
- [med] Opaque AE metadata: checking a few example records hid additional field changes. Proposal: standardize a whole-project field-diff report before naming a variant or asserting isolation.
- [low] Full local Go module tests hit an existing Darwin process-helper build gap. Proposal: document the supported focused-test and Windows-build paths until native Mac support is addressed separately.

## Blind spots

- Exact Adobe private internals and the cause of every production timeout were not established.
- Same-host staging experiments do not establish fleet-wide reliability. The implementation branch itself has not been rendered end-to-end or deployed as part of this closeout.

## Platform facts learned

| Fact                                                                                                                                      | Evidence                                              | verified / inferred              |
| ----------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- | -------------------------------- |
| DGE template generation substitutes `.Path` values and otherwise preserves serialized AE metadata                                         | Byte-exact source/template reconstruction, E6         | verified                         |
| In the examined layout, stored modification time occupies four bytes of `Pin.sspc`; native-save values match actual file/directory mtimes | Native exports and filesystem comparison, E7          | verified for the examined layout |
| Matching timestamps alone removed failures in the two tested sessions while original GUIDs remained unchanged                             | Strict variants, E8–E11                               | verified staging result          |
| An MFR import-state refresh problem is the strongest mechanism hypothesis                                                                 | Native faults/stacks and controlled outcomes, E12–E13 | inferred                         |

## What helped

- Immutable source hashes and byte-preserving variants made it possible to correct earlier claims without losing the original evidence.
- Interleaved repeated trials, a second session, full decoding, audio hashes and frame comparisons distinguished completion from output correctness.
- The source-code trace and real-template converter check tied the handoff to the actual generation path. Local draft records preserve findings while production testing remains deferred.
