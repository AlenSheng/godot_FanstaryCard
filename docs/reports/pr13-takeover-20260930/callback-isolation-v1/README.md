# Callback isolation OFFLINE component receipts

All six selected canonical cases pass in the final controlled Godot run. `Accepted` remains false and execution state remains `Partial`; POSTGRES, LIVE and MAIN independent acceptance are outstanding. B11.2 T01/T02 are SupportOnly, with RENDER additionally outstanding.

The paired baseline executes exactly the de1157fd GameStore and Gateway files with the same final case script and Python fixture used by the candidate. A03.1 T01/T02 remain golden. Four cases fail before the fix: uncorrelated rejection clears M/N; old-session rejection clears the next account's same match; M recovery/poll ownership survives N; and an old callback or Bootstrap revives after M → N → M in one session. `report.json` records every case's expected, actual, checks and remaining profiles.

The candidate uses GameStore source from 23f9a4cc and harness/provenance refinements from 7686fba3/51f6b834. Its Gateway is the parent-owned candidate copied into a disposable runtime project, never into this worktree's network file. `fixed/source_manifest.json` identifies that exact copied file with `SourceOverlay`, its SHA256 and the unchanged baseline SHA256. This component receipt requires the combined clean-SHA parent rerun.

A real loopback WebSocket receives `Gateway.send(room.snapshot.read)` and returns a correlated binary NOT_IN_ROOM response through `Gateway._receive` and `GameStore._on_event`. A negative binary response without context preserves the current GameStore/Gateway room. Other events are local protocol/event injections. Bootstrap, settlement GET and recovery polling use the actual Gateway protobuf HTTP transport. Six controlled responses are paused and retained in raw request records. The fixture never seeds recovery variables.

Budgets stayed fixed at 5 seconds per controlled response gate, 6 seconds per case and 55 seconds per Godot subprocess; the production 2500 ms poll cadence is unchanged. The final red/fixed Godot stderr files are empty. The existing 17-group settlement/play-retry runner and lobby race runner pass. The legacy polling fixture now supplies the room/match/session context that a real Gateway retains; its previous missing-context positive errors contradicted canonical A03.1 T03. Missing-context negatives remain in the new harness.

Reproduce after parent integration:

```sh
source /workspace/relicround-env/activate.sh
python tools/pr13_callback_isolation.py --output /tmp/pr13-callback-isolation
```

For a parent-owned Gateway candidate before integration, add `--gateway-overlay /absolute/path/to/gateway.gd`; the manifest records the tested copy. No database, live profile, rendered UI, asset write, remote operation or original raw ZIP is involved.
