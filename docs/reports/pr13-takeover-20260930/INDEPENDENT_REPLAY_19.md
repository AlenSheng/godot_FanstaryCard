# Fixed-source replay handoff for the bounded19 tasks

The [machine-readable index](BOUNDED_19_RECEIPT.json) gives all19 original task contracts/57 cases, exact report commits, sources, commands and outstanding criteria. Receipt source groups are intentionally separate. The stable production business/client/UI/protocol/config candidate is f812; only evidence tools changed to e060. A later documentation commit does not create new runtime evidence. S6 decisions are recorded only from explicit independent MAIN authority.

| Group | Source | Fixed report commit | Decision/proposal |
| --- | --- | --- | --- |
| LOAD01.1 | e06037f58738d0fbff86090e86d8bd06f8608e04 | c68bd4aadf59676096b93ce8e5a972b12575cc08 | MAIN Accepted/FixedWithEvidence; S6 review b4eba2cd6131dc6bae505af2a6ec9e7ba038a160 |
| LOAD01.2/.3/.4 | ee8adcf40be9aebb1330156a3524910c08225ebc | schema-safety-ee8adcf4; independent review dac6fdbd43d9c925a696a18f9774d9392c06c302 | MAIN Accepted/NoChangeWithEvidence; old-source decision preserved |
| LOAD02.1/.3/.4; .2 Partial | f812879e4518fd09bf22656451cb563d62940298 | a1d30eb89d74aa16bb2c094c5a78c20a5ed428b6 | Three Ready; .2 missing actual PG-game timeout→STOP/exclusive cycle terminal partition |
| LOAD03.1/.2 | ee8adcf40be9aebb1330156a3524910c08225ebc | e5de69b491bff1b3a3638bd11670901a5f96629e | Two Ready |
| LOAD03.3/.4 | ee8adcf40be9aebb1330156a3524910c08225ebc | dd097cf807b3d08acf2f6beaa2d1382f3a83d2e1 | Two Partial; missing production started/pending and route/full-run/three-cutoff outputs |
| B02.1–.4 | f812879e4518fd09bf22656451cb563d62940298 | a23aa0669f6c72c1689ba6f27037373336a98abb | Four Ready |
| A05.1–.3 | f812879e4518fd09bf22656451cb563d62940298 | 8068783331da07ec68354c1874eb0d65adea632f | .2/.3 Ready; .1 Partial with actual client terminal-display failure |

For new replay materialize each packet/harness into a new private directory. Use [prepare_source.py](prepare_source.py) with the full source SHA to create `<packet>/source`; this only archives source and removes generated bin/obj/.godot caches inside the new copy. It executes no tests. Original sealed evidence must remain unchanged. The cloud activation supplies Python3.12.14, Godot4.7.2, .NET10.0.400 and PG18.6.

LOAD01 is already independently closed. Original/new counterexamples and regression commands remain in [the e060 receipt guide](schema-second-e06037f5/README.md) and the two fixed independent S6 links. .2–.4 are not relabeled as accepted at e060 merely because twelve regression cases passed there.

For LOAD02 use a fresh packet with its `harness/`, an empty `evidence/`, and f812 `source/`. Actual coordinator/owned-child modes are invoked as:

```bash
python <packet>/harness/coordinator_case.py smoke_complete <packet>/evidence/smoke_complete
python <packet>/harness/coordinator_case.py redline <packet>/evidence/redline
python <packet>/harness/coordinator_case.py redline_corrupt <packet>/evidence/redline_corrupt
python <packet>/harness/coordinator_case.py emergency <packet>/evidence/emergency
python <packet>/harness/coordinator_case.py exit7 <packet>/evidence/exit7
python <packet>/harness/coordinator_case.py hang <packet>/evidence/hang
python <packet>/harness/caller_checks.py
```

Expected actual caller codes are0,2,3,3,3,3 and0 respectively. The hang keeps original35s grace. Original modes `time_limit`1, `operator`130, `invalid`3, `cleanup_unknown`1 and `late_business_error`1 are also indexed in evidence/commands.json. Each persisted report and failed/cancelled/unknown context must be inspected; the subprocess code alone is insufficient. Model clock/metrics/telemetry are explicit OFFLINE coordinator fixtures, while child STOP/exit/hang/emergency/caller execution is real. They establish these tool contracts, not server capacity. Preparation itself returns0/Prepared and launches no load. Applicable C-PY command at f812 is `python -m unittest tools.tests.test_gameplay_load_finalization tools.tests.test_gameplay_load_sampling_contract tools.tests.test_gameplay_load_stop -v` (42 entries).

The separate actual Godot timeout microfixture is preserved unchanged in `offline-acceptance-f812/load02/fixture/load02_timeout_fixture.gd`; copy it into the fresh f812 `source/client/tests` before `harness/real_timeout.py`. It retains production10s attempt/30s logical budgets. It has no PG game account and cannot close .2-T01. PG ACKSTOP/asset evidence and the full291-server/317-domain suite are indexed separately at the same f812. The actual PG-game timeout with exclusive per-cycle terminal partition remains unimplemented/unverified; do not add a LIVE/CI/human prerequisite to this missing local contract.

For LOAD03.1/.2 use a new packet with preserved `harness/`, `fixture/` wrappers, copied `evidence/SOURCE_PROOF.json`, empty `evidence/` and exact ee8 `source/`. The closing commit supplies three unchanged locally tested fixture wrappers omitted from the earlier packet; original seven production dependencies have preexisting source hashes. New wrapper-copy hashes are recorded honestly, without inventing historical pre-run hashes.

```bash
python <packet>/harness/prepare_fixture.py
"$A3GAME_GODOT_EXECUTABLE" --headless --path <packet>/fixture --editor --import --quit
python <packet>/harness/sequence_files.py
python <packet>/harness/run_sticky.py
python <packet>/harness/phase_http.py
```

These scripts expect the installed Godot executable at the original cloud path. Sequence uses eight real owned file-writer PIDs; the actual coordinator/report/exit3 remains invalid after a repaired final snapshot. Phase uses actual Gateway with HTTP_SCHEMA PB and delayed replies preserving original M phase/cycle. All three harness commands are expected0 only when assertions pass; sticky inner caller exits3. No PG/LIVE gate is required. The `.3/.4` diagnostics and six original assertions remain in their separate Partial packet; diagnostic derived statistics do not implement absent production output.

For B02 use a new packet with `harness/`, an empty `evidence/`, copied `evidence/input_manifest.json` and exact f812 `source/`. Keep the full original Git checkout at `/workspace/godot_FanstaryCard` with historical28c6c7e7 available for the unchanged negative-probe script. Set activation and `A3GAME_GODOT_EXECUTABLE`. Initialize a private PG at `<packet>/owned-pg` and `<packet>/pgsocket` (Unix-only port55482); `run_exact.py` starts, creates its own database and finally stops that PG.

```bash
initdb -D <packet>/owned-pg -A trust --no-locale --encoding=UTF8
mkdir <packet>/pgsocket
python <packet>/harness/negative-probes.py
python <packet>/harness/run_exact.py
```

The negative script expects old-API compilation to fail with CS1739/CS1061 and asserts those diagnostics; its wrapper exits0. Exact C#/Godot verifies default/candidate intent, GDD damage/heal vectors, pure ordered preview/PB callbacks and true PG hot-update/restore. Fresh whole Domain317/Server291, C-PROTO check and numerical Godot are in literal evidence/commands.json; build only inside `source/server`. Owned PG must be started and `FANTASYCARD_TEST_POSTGRES` supplied for full Server, with no skipped critical tests. No live server or default experimental flag is changed.

For A05 the fixed [80687833 guide](https://github.com/AlenSheng/godot_FanstaryCard/blob/8068783331da07ec68354c1874eb0d65adea632f/docs/reports/pr13-takeover-20260930/offline-acceptance-f812/a05/README.md) contains a runnable preparation helper, isolated PG commands, four-entry original matrix and controlled positive causal selector. Preserve its seven-file canonical overlay versus later nine-file causal assembly; neither is described as pure f812 CI. The causal assertion is intentionally red against f812. Its failure concerns stale visible M after actual durable ACK, while complete after-audit shows no duplicate asset credit and a distinct healthy-old-M/new-N test confirms route isolation. Full-suite295/317 green does not erase that red or justify accepting .1.

This closing batch is4Accepted/11Ready/4Partial. Global132 state is4Accepted/11Ready/42Partial/72NotRevalidated/3Blocked; G0–G5 unsigned. Main original case receipts are56Passed/1Partial, with extra real failures separately retained. Every new output must retain command/exit/profile/source, failure and cleanup evidence. No current CI retries, test-server operation or raw upload is part of this handoff.
