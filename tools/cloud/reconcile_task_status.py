"""Reconcile declared task states without promoting history or signing acceptance."""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*\Z")
PROFILES = ("OFFLINE", "POSTGRES", "AUDIT")

def _count(value):
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError("Counts must be nonnegative integers or null")
    return value

def _valid_case_id(value):
    return isinstance(value, str) and _CASE_ID.fullmatch(value) is not None


def _bound_receipt(receipt, root):
    if not isinstance(receipt, dict):
        return None, "MissingRawReceipt"
    try:
        relative = Path(receipt["path"])
        if relative.is_absolute():
            return None, "ReceiptOutsideInputRoot"
        path = (root / relative).resolve()
        path.relative_to(root)
        expected = receipt["sha256"]
        if not isinstance(expected, str) or not _HASH.fullmatch(expected):
            return None, "InvalidReceiptHash"
        data = path.read_bytes()
        if type(receipt.get("bytes")) is not int or len(data) != receipt["bytes"]:
            return None, "ReceiptByteCountMismatch"
        if hashlib.sha256(data).hexdigest() != expected:
            return None, "ReceiptHashMismatch"
        actual = json.loads(data.decode("utf-8-sig"))
        if not isinstance(actual, dict):
            return None, "UnreadableOrInvalidReceipt"
        return actual, None
    except (KeyError, OSError, ValueError, TypeError, AttributeError):
        return None, "UnreadableOrInvalidReceipt"


def _receipt(record, root, integration_sha):
    if not _valid_case_id(record.get("case_id")):
        return "InvalidDeclaredCaseIdentity"
    actual, error = _bound_receipt(record.get("receipt"), root)
    if error:
        return error
    if not _valid_case_id(actual.get("case_id")):
        return "InvalidReceiptCaseIdentity"
    if any(actual.get(key) != record.get(key) for key in ("case_id", "status", "executed", "source_sha")):
        return "ReceiptRecordMismatch"
    if actual.get("executed") is not True or actual.get("source_sha") != integration_sha:
        return "ReceiptNotCurrentExecution"
    return "VerifiedCurrentCaseReceipt"


def _resolution_receipt(discrepancy, root, integration_sha):
    # A declaration cannot clear a provenance/count blocker. Require a current,
    # byte-bound executed receipt with the same named observation/reference and
    # an explicit basis; history alone is never current resolution evidence.
    if integration_sha is None:
        return "MissingResolutionIntegrationSHA"
    if discrepancy.get("reference_value") is None:
        return "MissingResolutionReference"
    if not _valid_case_id(discrepancy.get("name")):
        return "InvalidDiscrepancyIdentity"
    actual, error = _bound_receipt(discrepancy.get("resolution_receipt"), root)
    if error:
        return error
    if not _valid_case_id(actual.get("case_id")):
        return "InvalidResolutionCaseIdentity"
    if (actual.get("executed") is not True or actual.get("status") != "Passed"
            or actual.get("source_sha") != integration_sha):
        return "ResolutionNotCurrentPassedExecution"
    if (actual.get("resolved") is not True or actual.get("discrepancy_name") != discrepancy["name"]
            or any(type(actual.get(key)) is not int or actual[key] != discrepancy[key]
                   for key in ("observed_value", "reference_value"))):
        return "ResolutionRecordMismatch"
    basis = actual.get("resolution_basis")
    if not isinstance(basis, str) or not basis.strip():
        return "MissingResolutionBasis"
    return "VerifiedCurrentDiscrepancyResolution"

def reconcile(payload, input_root):
    root = Path(input_root).resolve()
    integration_sha = payload.get("integration_sha")
    if integration_sha is not None and (not isinstance(integration_sha, str) or not _SHA.fullmatch(integration_sha)):
        raise ValueError("integration_sha must be an exact Git SHA or null")
    discrepancies = deepcopy(payload.get("discrepancies", []))
    unresolved = []
    for discrepancy in discrepancies:
        _count(discrepancy.get("observed_value"))
        _count(discrepancy.get("reference_value"))
        if type(discrepancy.get("resolved")) is not bool:
            raise ValueError("Discrepancy resolution must be explicit")
        if discrepancy["resolved"]:
            discrepancy["declared_resolved"] = True
            discrepancy["resolution_verification"] = _resolution_receipt(discrepancy, root, integration_sha)
            discrepancy["resolved"] = discrepancy["resolution_verification"] == "VerifiedCurrentDiscrepancyResolution"
        if not discrepancy["resolved"]:
            unresolved.append(discrepancy)
    tasks = []
    seen = set()
    for original in payload["tasks"]:
        task_id = original["task_id"]
        if not isinstance(task_id, str) or not task_id or task_id in seen:
            raise ValueError("Task IDs must be unique nonempty strings")
        seen.add(task_id)
        history = []
        for declared in original.get("historical_tests", []):
            counts = {key: _count(declared.get("reported_counts", {}).get(key))
                      for key in ("passed", "failed", "errors", "skipped", "executed")}
            history.append({
                "source_sha": declared.get("source_sha"),
                "source_provenance": deepcopy(declared.get("source_provenance")),
                "reported_counts": counts,
                "classification": {"passed": "HistoricalExecutedPassed", "skipped": "HistoricalSkipped"},
                "proof_level": declared.get("proof_level", "DeclarationOnly"),
                "current_execution": False,
                "promoted_to_current_pass": False,
            })
        current = []
        for declared in original.get("current_tests", []):
            row = deepcopy(declared)
            if integration_sha is None:
                row["verification"] = "MissingIntegrationSHA"
            elif row.get("source_sha") != integration_sha:
                row["verification"] = "SourceSHAMismatch"
            elif row.get("executed") is not True or row.get("status") not in ("Passed", "Failed"):
                row["verification"] = "NotExecutedOrInvalidStatus"
            else:
                row["verification"] = _receipt(row, root, integration_sha)
            current.append(row)
        verified = [r for r in current if r["verification"] == "VerifiedCurrentCaseReceipt"]
        if not current:
            current_state = "NotRevalidated"
        elif any(r["status"] == "Failed" for r in verified):
            current_state = "Failed"
        elif len(verified) == len(current):
            current_state = "Passed"
        elif verified:
            current_state = "Partial"
        else:
            current_state = "Blocked"
        tasks.append({
            "task_id": task_id,
            "specification_state": original.get("specification_state"),
            "implementation_status": original.get("implementation_status"),
            "authoritative_state": original.get("authoritative_state"),
            "queue_state": original.get("queue_state"),
            "historical_tests": history,
            "current_test_declaration": deepcopy(original.get("current_test_declaration")),
            "current_revalidation": {"state": current_state, "cases": current},
            "existing_acceptance_record": deepcopy(original.get("acceptance_record")),
            "new_acceptance_signed": False,
            "blocking_discrepancies": deepcopy(unresolved),
        })
    return {
        "schema_version": 1,
        "kind": "TaskStatusReconciliation_NotAcceptanceRegister",
        "input_provenance": deepcopy(payload.get("input_provenance")),
        "integration_sha": integration_sha,
        "tasks": tasks,
        "authoritative_state_counts": dict(Counter(t["authoritative_state"] for t in tasks)),
        "queue_state_counts": dict(Counter(t["queue_state"] for t in tasks)),
        "discrepancies": discrepancies,
        "claims": {
            "numeric_observations_preserved": True,
            "reconciliation_status": "BlockedByUnresolvedDiscrepancy" if unresolved else "NoUnresolvedDiscrepancyDeclared",
            "historical_counts_are_current_pass": False,
            "specification_ready_is_accepted": False,
            "new_acceptance_signed": False,
        },
        "remaining_profile_conditions": {
            "OFFLINE": "Bind this reconciliation execution to actual source and input byte hashes; review all three canonical expectations.",
            "POSTGRES": "Same integration SHA execution receipts and skips must be independently reconciled; no PG execution is implied by this report.",
            "AUDIT": "Resolve or explicitly retain provenance differences and independently review source-bound report/cases/commands/manifest.",
            "G0_G5_S5": "MAIN applies required profiles/gates to the fixed integration; this diagnostic report never signs Accepted.",
        },
    }

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    source = args.input.resolve()
    output = args.output.resolve()
    if output == source or output.exists():
        parser.error("Use a new output path; existing input/evidence cannot be overwritten")
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    result = reconcile(payload, source.parent)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"output": str(output), "tasks": len(result["tasks"]),
                      "new_acceptance_signed": False}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
