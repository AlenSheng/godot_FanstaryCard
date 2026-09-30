# Three independently reproduced schema gaps: fixed-source replay

Fixed code SHA `e06037f58738d0fbff86090e86d8bd06f8608e04`. Business/client/UI remain f812. Same clean SHA: fullPython122/0/0, originalLOAD01 twelve/0/0, old five invalid inputs all explicitexit3; three new actual owned file-path probes have zero unhandled exceptions.

Finite durations1e308+1e308 yield correct finite mean1e308 with2 known failures/2 samples, and sample quality remains insufficient. Invalid archive match_id=[] and event_type=[] yield explicit invalid-evidence3; optional empty/None match for pre-match cycle start remains compatible. No samples dropped, threshold lowered, or fake acceptance.

Copy `reproduce.py`, `reproduce_old_five.py`, `run_load01.py` from this receipt commit into a temporary directory and use a clean checkout of the fixed code SHA. New output dirs are required:

```bash
python -m unittest discover -s tools/tests -v
PYTHONDONTWRITEBYTECODE=1 python /tmp/reproduce.py --source "$PWD" --output /tmp/schema-new3-independent
PYTHONDONTWRITEBYTECODE=1 python /tmp/reproduce_old_five.py --source "$PWD" --output /tmp/schema-old5-independent
PR13_SOURCE_ROOT="$PWD" PYTHONDONTWRITEBYTECODE=1 python /tmp/run_load01.py --output /tmp/load01-independent
```

The schema probe harness exits0 to record observations; independently inspect actual result fields. NEW3 expects unhandled_exceptions0/invalid_failures2 plus finite_mean1e308,error_count2,sample_count2,latency_sample_quality insufficient. OLD5 expects unhandled0/invalid5; all children reaped. LOAD01 exits0 only for12Passed.

MAIN formally accepted LOAD01.2/.3/.4 at ee8 and failed .1; the fixed independent review is `dac6fdbd43d9c925a696a18f9774d9392c06c302`, recorded in [MAIN_S6_ee8adcf4.json](../MAIN_S6_ee8adcf4.json). Only .1 is submitted for new independent actual replay. Previous receipts/raw are immutable; G0–G5 and full132 remain unsigned/incomplete.
