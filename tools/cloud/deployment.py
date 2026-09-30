"""Trusted-runner validation and build provenance. Never prints authentication values."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import urllib.request

REPOSITORY = "AlenSheng/godot_FanstaryCard"
ENVIRONMENT = "silicon-valley-test"


def sha(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Expected a full lowercase commit SHA")
    return value


def positive_integer(value):
    if not re.fullmatch(r"[1-9][0-9]{0,17}", str(value)):
        raise ValueError("Expected a positive integer")
    return int(value)


def validate_pr(pr, number, commit):
    sha(commit)
    positive_integer(number)
    if pr.get("number") != int(number) or pr.get("state") != "open":
        raise ValueError("Deployment requires the selected open PR")
    for side in ("head", "base"):
        if pr[side]["repo"]["full_name"] != REPOSITORY:
            raise ValueError("Forks and other repositories cannot be deployed")
    if pr["base"]["ref"] != "release" or pr["head"]["sha"] != commit:
        raise ValueError("PR source moved or has an unexpected target branch; freeze and retrigger")


def api(path):
    # Only a fixed GitHub API origin; user inputs cannot set an API URL.
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPOSITORY + path,
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                 "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def verify_environment(environment, branches):
    if environment.get("name") != ENVIRONMENT:
        raise ValueError("Test deployment environment is missing")
    reviewers = [r for r in environment.get("protection_rules", []) if r["type"] == "required_reviewers"]
    if not reviewers or not reviewers[0].get("reviewers"):
        raise ValueError("A required environment reviewer must approve deployment")
    if environment.get("can_admins_bypass", True):
        raise ValueError("Disable environment protection bypass by administrators")
    policy = environment.get("deployment_branch_policy") or {}
    allowed = branches.get("branch_policies", [])
    if not policy.get("custom_branch_policies") or len(allowed) != 1:
        raise ValueError("Allow exactly the main branch in this test environment")
    if allowed[0].get("name") != "main" or allowed[0].get("type", "branch") != "branch":
        raise ValueError("Environment must restrict deployment to main")


def preflight(output):
    if os.environ["GITHUB_REPOSITORY"] != REPOSITORY or os.environ["GITHUB_EVENT_NAME"] != "workflow_dispatch":
        raise ValueError("Only manual dispatch from the canonical repository is allowed")
    if os.environ["GITHUB_REF"] != "refs/heads/main":
        raise ValueError("Deployment controller must run from the reviewed default branch")
    if api("")["default_branch"] != "main":
        raise ValueError("Repository default branch changed: review controller trust policy")
    if os.environ.get("TEST_DEPLOY_ENABLED") != "true":
        raise ValueError("Test deployment has not been enabled by the environment owner")
    controller = sha(os.environ["GITHUB_SHA"])
    if os.environ.get("TEST_DEPLOY_APPROVED_WORKFLOW_SHA") != controller:
        raise ValueError("Pin TEST_DEPLOY_APPROVED_WORKFLOW_SHA to the reviewed controller commit")
    number = positive_integer(os.environ["PR_NUMBER"])
    commit = sha(os.environ["COMMIT_SHA"])
    pr = api(f"/pulls/{number}")
    validate_pr(pr, number, commit)
    environment = api("/environments/" + ENVIRONMENT)
    branches = api("/environments/" + ENVIRONMENT + "/deployment-branch-policies")
    verify_environment(environment, branches)
    result = {"repository": REPOSITORY, "source_sha": commit, "pr_number": number,
              "controller_sha": controller, "run_id": positive_integer(os.environ["GITHUB_RUN_ID"]),
              "run_attempt": positive_integer(os.environ["GITHUB_RUN_ATTEMPT"]),
              "source_branch": pr["head"]["ref"], "environment": ENVIRONMENT}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        stream.write(f"source_sha={commit}\npr_number={number}\n")


def file_hash(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def extract_health(updater, output):
    # Reuse the existing deployment checks without executing its branch-following updater.
    content = pathlib.Path(updater).read_text(encoding="utf-8")
    start = content.index("domain_certificate_ok() {\n")
    end = content.index("normalize_monitoring_permissions() {\n", start)
    functions = content[start:end]
    if "health_check() {\n" not in functions:
        raise ValueError("Existing deployment health-check interface changed")
    pathlib.Path(output).write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + functions + "\nhealth_check\n", encoding="utf-8")


def manifest(preflight_file, archive, image_tag, output):
    source = json.loads(pathlib.Path(preflight_file).read_text())
    sha(source["source_sha"])
    image_id = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", image_tag], text=True).strip()
    revision = subprocess.check_output(["docker", "image", "inspect", "--format", '{{index .Config.Labels "org.opencontainers.image.revision"}}', image_tag], text=True).strip()
    if revision != source["source_sha"] or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("Built image provenance did not match the frozen source")
    source.update({"format": 1, "image_id": image_id, "archive_sha256": file_hash(archive),
                   "health_sha256": file_hash(pathlib.Path(output).parent / "health.sh")})
    pathlib.Path(output).write_text(json.dumps(source, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("preflight")
    p.add_argument("--output", type=pathlib.Path, required=True)
    p = commands.add_parser("health")
    p.add_argument("--updater", required=True)
    p.add_argument("--output", required=True)
    p = commands.add_parser("manifest")
    p.add_argument("--preflight", required=True)
    p.add_argument("--archive", required=True)
    p.add_argument("--image-tag", required=True)
    p.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "preflight":
        preflight(args.output)
    elif args.command == "health":
        extract_health(args.updater, args.output)
    else:
        manifest(args.preflight, args.archive, args.image_tag, args.output)
