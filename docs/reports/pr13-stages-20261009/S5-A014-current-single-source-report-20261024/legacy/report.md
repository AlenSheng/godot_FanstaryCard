# PR13 single-source report

Run: `5d47c4fbcb754beb8c6b8f22db37ccd0`
Generator: `pr13-single-source-report-v1`; replay: `legacy-accounting-explicit-cutoffs-v1`
Cutoffs (Unix ms): STOP=1791588910679, final=1791588910730

| Cutoff | Acknowledgements | Completed cycles |
| --- | ---: | ---: |
| running | 6 | 6 |
| drain | 0 | 0 |
| final | 6 | 6 |

| Cutoff | Client | Acknowledgements | Completed cycles |
| --- | --- | ---: | ---: |
| running | g001c018dde07 | 3 | 3 |
| running | g001c02b3c17e | 3 | 3 |
| final | g001c018dde07 | 3 | 3 |
| final | g001c02b3c17e | 3 | 3 |

Client distribution covers recorded events; zero-cycle clients require a launch manifest.
No separate check records supplied; zero check denominators do not prove no business failures.
This derivation grants no runtime, capacity, historical recovery or whole-project acceptance.

## Source identities

- execution.json: 4404 bytes, SHA256 `900160ab3b5ae28a3e8649473c952a30f5ed57a7e3458d5337465ac9bc8d8d87`
- load/20261010-071939-fa63ca/report.json: 1911633 bytes, SHA256 `759ff1764df90ac0d23dea10dc462feeb908dcd6393516b3f97bae09d7969139`
- load/20261010-071939-fa63ca/g001c018dde07.json.telemetry.jsonl: 1917505 bytes, SHA256 `bab3b33b14ac3b3a18ecaf7f184a6375affa7ed55771ab2dd26f858274f31620`
- load/20261010-071939-fa63ca/g001c02b3c17e.json.telemetry.jsonl: 3273428 bytes, SHA256 `e27474aadfee4b9e36a3221aa475f6c5daa64f4fec45a51051762abb12e3be87`

## Algorithm source identities

- cloud_load_test.py: `9a1f51571c62c1cbe8c1be39c5b15c855ce1c13ca364eb18237cf276ab30e9dd`
- pr13_audit_replay.py: `873808f1180fba28c34f3eb5c06102aeabd3317c937ba360c7d719b932354e8b`
- pr13_runtime_evidence.py: `63c95c1a9d1a51f8195edb8b1956a761d59230debffe45c7231172b8109e11c8`
- pr13_single_source_report.py: `574ee0a7e9446bebe6d2a8318f47a61f808ad2a0fbcfcad0c94bd3179be90208`

## Retained legacy redlines

```json
{
  "actor_wait_p95_ms": 100,
  "command_p95_ms": 2000,
  "consecutive_windows": 3,
  "cpu_percent": 85,
  "disk_available_percent": 15,
  "http_p95_ms": 1500,
  "memory_available_percent": 15
}
```
