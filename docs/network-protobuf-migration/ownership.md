# Execution ownership

- fc_protocol: protocol/**, protocol generation tools, generated client schemas/endpoint registry, Contracts/**, protocol compatibility/report.
- fc_qa: phase 1 read-only baseline with isolated outputs; phase 3 new migration tests and benchmark tools, QA reports.
- fc_server_api: first-party HTTP adapters and new ProtobufHttp/**; no Contracts, Realtime or shared registration.
- fc_client: client/network/**, necessary network boundaries in state/platform; gateway sole owner.
- fc_realtime: server Realtime/**; shared registration via coordinator.
- fc_perimeter: Caddyfile, site/**, Admin/**, perimeter docs; announcements edits must coordinate.
- Coordinator: Program.cs, shared project/config files (except Contracts csproj), execution-state.json, integration documentation, commits.

Runtime allows four live agents including coordinator, so phase 2 starts three workers, then the fourth as a slot becomes available. This remains below the user limit of four child agents. All six roles are real tool-created agents; canonical returned task names are recorded verbatim.

Original source changes were committed as e3fed8e and pushed to origin/release on explicit user instruction before migration. Independent branch starts from origin/codex/protobuf-migration-20260928 (9ef7704), with that source commit cherry-picked as b8e848e. Original generated outputs/caches/screenshots remain untouched.

The missing legacy server_create skill is explicitly permitted by PLAN.md. Prior REST JSON-only design clauses are superseded solely for this requested migration; gameplay freezes and authority/transaction rules remain applicable.

Expanded B scope: read-only pagination in EconomyRepository.GetMarketAsync and MailRepository.GetAsync; no economic mutation or gameplay rule change. Coordinator also owns root Docker build context inputs, deployment manifest inclusion (not execution), existing legacy-test launch compatibility flags, and equivalent xUnit2012 assertion repair. First fc_perimeter spawn was rejected by runtime thread limit; retried only after fc_realtime completed, then succeeded as /root/fc_perimeter.

Final B scope includes transactional response-budget preflight for mail claims, before any grant, without changing reward amounts or partial-success semantics. Full Godot import rewrote import-file line endings only; Git content comparison was empty, index metadata refreshed, no asset changes staged.
