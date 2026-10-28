"""Independent validation of original B09.2 cloud boundary records."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path


def validate(row, source):
    assert row["source_sha"] == source
    a = row["actual"]
    case = row["case_id"]
    cap = a["capacity"]
    assert cap in (3, 5, 8) and a["hero"] in ("Mage", "Priest", "Guardian")
    assert a["seed"] in (460001, 461001, 462001)
    before, after = a["before"], a["after"]
    p, q = before["Players"][0], after["Players"][0]
    assert len(before["Players"]) == len(after["Players"]) == 1
    assert p["Phase"] in (2, 6)  # native ActionBar / Choice
    assert before["Numerics"]["OptionalMonsterPool"] is True
    assert before["Numerics"]["MonsterCapacity"] == cap
    assert before["Numerics"] == after["Numerics"]
    assert after["Revision"] == before["Revision"] + 1
    candidate = a["candidate"]
    assert candidate in p["MonsterPool"]["Pending"]
    assert candidate["CardId"] == "M-FIREBAT" and candidate["Level"] == 0
    basis = a["Base"]
    prefix = {"Mage": "MAG", "Priest": "PRI", "Guardian": "GUA"}[a["hero"]]
    expected_cards = {f"C{i:02}" for i in range(1, 14)} | {f"{prefix}-{i:02}" for i in range(1, 8)}
    assert len(basis) == 20 and {c["CardId"] for c in basis} == expected_cards
    kill = a["Kill"]
    assert kill["actor_id"] == p["PlayerId"] and kill["resolution"]["TargetDefeated"] is True
    assert kill["offered"]["CardId"] == "M-FIREBAT" and kill["played"] in basis
    assert kill["target_id"] == "fire-bat"
    x, y = p["Combat"]["Deck"], q["Combat"]["Deck"]
    old_pool, new_pool = p["MonsterPool"], q["MonsterPool"]
    accepted = case.endswith("T01") or case.endswith("T02")
    replacement = a.get("replacement")
    expected_deck = copy.deepcopy(x)
    if accepted:
        for pile in ("Hand", "Library", "Discard"):
            expected_deck[pile] = [c for c in x[pile] if c != replacement]
        expected_deck["Discard"].append(candidate)
    assert y == expected_deck
    expected_active = [c for c in old_pool["Active"] if c != replacement]
    if accepted:
        expected_active.append(candidate)
    assert new_pool["Active"] == expected_active
    assert new_pool["Pending"] == [c for c in old_pool["Pending"] if c != candidate]
    assert new_pool["GrantedSources"] == old_pool["GrantedSources"]
    assert new_pool["Receipts"][:-1] == old_pool["Receipts"]
    receipt = new_pool["Receipts"][-1]
    assert receipt["CandidateId"] == candidate["InstanceId"] and receipt["Accept"] == accepted
    assert receipt["ReplaceId"] == (replacement["InstanceId"] if replacement else None)
    all_cards = y["Hand"] + y["Library"] + y["Discard"]
    assert len(all_cards) == 20 + len(expected_active)
    assert len({c["InstanceId"] for c in all_cards}) == len(all_cards)
    assert all(c in all_cards for c in basis)
    normalized = copy.deepcopy(after)
    normalized["Revision"] = before["Revision"]
    normalized["Players"][0]["Combat"]["Deck"] = x
    normalized["Players"][0]["MonsterPool"] = old_pool
    assert normalized == before  # includes every RNG stream, resource and inventory
    if case.endswith("T01"):
        assert len(old_pool["Active"]) == a["occupancy"] < cap
    elif case.endswith("T02"):
        assert len(old_pool["Active"]) == len(new_pool["Active"]) == cap
        assert replacement in old_pool["Active"] and replacement in x[a["pile"]]
        assert a["missing_replacement_rejected"] and a["base_replacement_rejected"]
        assert a["missing_replacement_after"] == before
        assert a["base_replacement_after"] == before
    else:
        assert case.endswith("T03") and len(old_pool["Active"]) == (cap if a["full"] else 0)
    return case


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    counts, files, rows, strata = {}, [], [], set()
    for path in sorted(args.native.glob("*.jsonl.gz")):
        digest, size, number = hashlib.sha256(), 0, 0
        with gzip.open(path, "rb") as stream:
            for line in stream:
                row = json.loads(line)
                case = validate(row, args.source_sha)
                counts[case] = counts.get(case, 0) + 1
                a = row["actual"]
                discriminator = a.get("occupancy", a.get("pile", a.get("full")))
                key = (case, a["hero"], a["capacity"], a["seed"], str(discriminator))
                assert key not in strata
                strata.add(key)
                rows.append(row)
                digest.update(line)
                size += len(line)
                number += 1
        files.append({"path": path.name, "rows": number, "raw_bytes": size,
                      "raw_sha256": digest.hexdigest(), "stored_bytes": path.stat().st_size,
                      "stored_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    assert counts == {"PR13-B09.2-T01": 144, "PR13-B09.2-T02": 81, "PR13-B09.2-T03": 54}
    controls = []
    for name in ("hand-compensation", "skip-HP-compensation", "base-identity-loss", "wrong-source"):
        row = copy.deepcopy(next(r for r in rows if r["case_id"].endswith("T03")))
        p = row["actual"]["after"]["Players"][0]
        if name == "hand-compensation":
            p["Combat"]["Deck"]["Hand"].append(row["actual"]["candidate"])
        elif name == "skip-HP-compensation":
            p["Combat"]["Hp"] += 1
        elif name == "base-identity-loss":
            p["Combat"]["Deck"]["Library"][0]["InstanceId"] = "00000000-0000-0000-0000-000000000001"
        else:
            row["source_sha"] = "wrong"
        try:
            validate(row, args.source_sha)
        except AssertionError:
            controls.append({"name": name, "rejected": True})
        else:
            raise AssertionError(f"negative control not rejected: {name}")
    result = {"ok": True, "source_sha": args.source_sha, "case_rows": counts,
              "original_files": files, "strata": len(strata), "negative_controls": controls,
              "scope": "OFFLINE capacity boundaries; not formal route experiment or GUI acceptance",
              "formal_experiment_pending": True, "canonical_render_pending": True, "whole_task_accepted": False}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "original_files"}))


if __name__ == "__main__":
    main()
