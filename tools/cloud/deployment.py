"""Trusted-runner validation and build provenance. Never prints authentication values."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import urllib.request
import xml.etree.ElementTree as ET

REPOSITORY = "AlenSheng/godot_FanstaryCard"
ENVIRONMENT = "silicon-valley-test"
TRUSTED_BRANCH = "release"
APPROVAL_MODE = 'owner_dispatch'
OWNER_ID = 20944685


def sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Expected a full lowercase commit SHA")
    return value


def positive_integer(value):
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]{0,17}", str(value)):
        raise ValueError("Expected a positive integer")
    return int(value)


def validate_pr(pr, number, commit):
    sha(commit)
    positive_integer(number)
    if pr.get("number") != int(number) or pr.get("state") != "open":
        raise ValueError("Deployment requires the selected open PR")
    for side in ("head", "base"):
        if (pr.get(side, {}).get("repo") or {}).get("full_name") != REPOSITORY:
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
    # No redirects with an Authorization header, including API error redirects.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
        return json.load(response)


def verify_environment(environment, branches, mode=APPROVAL_MODE):
    if environment.get("name") != ENVIRONMENT:
        raise ValueError("Test deployment environment is missing")
    if mode != APPROVAL_MODE:
        raise ValueError('Unapproved deployment authorization mode')
    # This explicitly authorized mode has no GitHub required-reviewer gate.
    # Live branch policy is still mandatory, never inferred from vars or UI notes.
    policy = environment.get("deployment_branch_policy") or {}
    allowed = branches.get("branch_policies", [])
    if policy.get("custom_branch_policies") is not True or policy.get("protected_branches") is not False or len(allowed) != 1 or branches.get("total_count") != 1:
        raise ValueError("Allow exactly the release branch in this test environment")
    if allowed[0].get("name") != TRUSTED_BRANCH or allowed[0].get("type") != "branch":
        raise ValueError("Environment must restrict deployment to release, without tags")


def preflight(output):
    if os.environ["GITHUB_REPOSITORY"] != REPOSITORY or os.environ["GITHUB_EVENT_NAME"] != "workflow_dispatch":
        raise ValueError("Only manual dispatch from the canonical repository is allowed")
    if os.environ["GITHUB_REF"] != "refs/heads/" + TRUSTED_BRANCH:
        raise ValueError("Deployment controller must run from reviewed release")
    repository = api("")
    if repository.get("full_name") != REPOSITORY or not repository.get("default_branch"):
        raise ValueError("Cannot verify canonical repository metadata")
    if os.environ.get("TEST_DEPLOY_ENABLED") != "true":
        raise ValueError("Test deployment has not been enabled by the environment owner")
    controller = sha(os.environ["GITHUB_SHA"])
    if os.environ.get("TEST_DEPLOY_APPROVED_WORKFLOW_SHA") != controller:
        raise ValueError("Pin TEST_DEPLOY_APPROVED_WORKFLOW_SHA to the reviewed controller commit")
    number = positive_integer(os.environ["PR_NUMBER"])
    commit = sha(os.environ["COMMIT_SHA"])
    if os.environ.get('TEST_DEPLOY_APPROVAL_MODE') != APPROVAL_MODE:
        raise ValueError('Owner dispatch mode must be explicitly enabled')
    if os.environ.get('GITHUB_ACTOR_ID') != str(OWNER_ID) or os.environ.get('GITHUB_ACTOR') != 'AlenSheng' or os.environ.get('GITHUB_TRIGGERING_ACTOR') != 'AlenSheng':
        raise ValueError('Only the repository owner may confirm a test deployment')
    if repository.get('owner', {}).get('id') != OWNER_ID:
        raise ValueError('Repository ownership changed; review authorization policy')
    if positive_integer(os.environ['GITHUB_RUN_ATTEMPT']) != 1:
        raise ValueError('Reruns require a new owner dispatch and confirmation')
    if os.environ.get('CONFIRM_SOURCE_SHA') != commit or os.environ.get('CONFIRM_RESTART') != 'true':
        raise ValueError('Confirm this exact SHA and necessary application restart')
    baseline = sha(os.environ.get('ROLLBACK_BASELINE_SHA'))
    if os.environ.get('CONFIRM_ROLLBACK_COMPATIBILITY') != 'true':
        raise ValueError('Reviewed data/rollback compatibility is required')
    pr = api(f"/pulls/{number}")
    validate_pr(pr, number, commit)
    environment = api("/environments/" + ENVIRONMENT)
    branches = api("/environments/" + ENVIRONMENT + "/deployment-branch-policies")
    verify_environment(environment, branches)
    result = {"repository": REPOSITORY, "source_sha": commit, "pr_number": number,
              "controller_sha": controller, "run_id": positive_integer(os.environ["GITHUB_RUN_ID"]),
              "run_attempt": positive_integer(os.environ["GITHUB_RUN_ATTEMPT"]),
              "environment": ENVIRONMENT, 'approval_mode': APPROVAL_MODE,
              'approved_actor_id': OWNER_ID, 'confirmed_source_sha': commit,
              'restart_confirmed': True, 'rollback_baseline_sha': baseline,
              'rollback_compatibility_confirmed': True}
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


MANIFEST_FIELDS = frozenset(('format', 'repository', 'source_sha', 'pr_number', 'controller_sha',
    'run_id', 'run_attempt', 'environment', 'image_id', 'archive_sha256', 'health_sha256',
    'remote_sha256', 'deployment_sha256', 'approval_mode', 'approved_actor_id',
    'confirmed_source_sha', 'restart_confirmed', 'rollback_baseline_sha',
    'rollback_compatibility_confirmed', 'image_validation_sha256'))


def validate_manifest(data, source_sha, run_id, run_attempt, controller_sha):
    sha(source_sha)
    sha(controller_sha)
    if not isinstance(data, dict) or set(data) != MANIFEST_FIELDS:
        raise ValueError("Unexpected manifest fields")
    if type(data['format']) is not int or data['format'] != 2 or data['repository'] != REPOSITORY or data['environment'] != ENVIRONMENT:
        raise ValueError("Unexpected manifest identity")
    if data['source_sha'] != source_sha or data['controller_sha'] != controller_sha:
        raise ValueError("Artifact source/controller differs from approval")
    if data['approval_mode'] != APPROVAL_MODE or type(data['approved_actor_id']) is not int or data['approved_actor_id'] != OWNER_ID or data['confirmed_source_sha'] != source_sha or data['restart_confirmed'] is not True:
        raise ValueError('Artifact has no exact owner deployment confirmation')
    sha(data['rollback_baseline_sha'])
    if data['rollback_compatibility_confirmed'] is not True:
        raise ValueError('Missing reviewed application rollback compatibility')
    for field, expected in (('run_id', run_id), ('run_attempt', run_attempt)):
        if type(data[field]) is not int or data[field] != positive_integer(expected):
            raise ValueError("Artifact belongs to another run/attempt")
    if type(data['pr_number']) is not int:
        raise ValueError("Invalid PR identity")
    positive_integer(data['pr_number'])
    for field in ('archive_sha256', 'health_sha256', 'remote_sha256', 'deployment_sha256', 'image_validation_sha256'):
        if not isinstance(data[field], str) or not re.fullmatch(r'[0-9a-f]{64}', data[field]):
            raise ValueError("Malformed checksum")
    if not isinstance(data['image_id'], str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', data['image_id']):
        raise ValueError("Malformed immutable image ID")


def verify_artifact(artifact, artifact_id, run_id, run_attempt, controller_sha):
    positive_integer(artifact_id)
    workflow = artifact.get('workflow_run') or {}
    if artifact.get('id') != artifact_id or artifact.get('expired') is not False:
        raise ValueError('Artifact is unavailable')
    if artifact.get('name') != f'tested-image-{run_id}-{run_attempt}' or workflow.get('id') != run_id or workflow.get('head_sha') != controller_sha:
        raise ValueError('Artifact API provenance differs from this controller run')
    if not isinstance(artifact.get('digest'), str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', artifact['digest']):
        raise ValueError('Artifact has no verifiable Actions digest')
    if not 0 < artifact.get('size_in_bytes', 0) <= 4 * 1024 ** 3:
        raise ValueError('Unexpected artifact size')


def verify_tests(directory):
    """Require real Domain + Server results, including executed PostgreSQL cases."""
    summary = {}
    for label in ('domain', 'postgres'):
        root = ET.parse(pathlib.Path(directory) / (label + '.trx')).getroot()
        results = root.findall('.//{*}UnitTestResult')
        if not results or any(row.get('outcome') != 'Passed' for row in results):
            raise ValueError('Failed, skipped or missing regression result')
        if label == 'postgres' and not any('PostgresRuntimeIntegrationTests.' in row.get('testName', '') for row in results):
            raise ValueError('PostgreSQL integration tests did not execute')
        summary[label] = len(results)
    return summary


def validate_image_proof(proof, image_id, source_sha):
    fields = {'ok', 'source_sha', 'image_id', 'assemblies', 'tests', 'runtime_uid',
              'restart_test_passed', 'database_outage', 'production_local_auth_status', 'cleanup_ok'}
    if not isinstance(proof, dict) or set(proof) != fields or proof['ok'] is not True or proof['image_id'] != image_id or proof['source_sha'] != source_sha:
        raise ValueError('Invalid final-image validation identity')
    if proof['restart_test_passed'] is not True or proof['cleanup_ok'] is not True or proof['production_local_auth_status'] != 404 or proof['database_outage'] != {'ready':503,'live':200,'recovered':200}:
        raise ValueError('Incomplete runtime/restart/Production/DB-outage evidence')
    if not isinstance(proof['runtime_uid'], str) or not proof['runtime_uid'].isdecimal() or int(proof['runtime_uid']) == 0:
        raise ValueError('Runtime must use a non-root UID')
    counts = proof['tests']
    if not isinstance(counts, dict) or set(counts) != {'total','passed','failed','notExecuted'} or any(type(value) is not int for value in counts.values()) or counts['total'] <= 0 or counts['total'] != counts['passed'] or counts['failed'] or counts['notExecuted']:
        raise ValueError('Final-image tests failed, skipped or absent')
    assemblies = proof['assemblies']
    if not isinstance(assemblies, dict) or set(assemblies) != {'FantasyCard.Contracts.dll','FantasyCard.Domain.dll','FantasyCard.Server.dll'} or any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}',value) for value in assemblies.values()):
        raise ValueError('Missing final DLL hashes')


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
    proof_path = pathlib.Path(output).parent / 'image-validation.json'
    proof = json.loads(proof_path.read_text())
    validate_image_proof(proof, image_id, source['source_sha'])
    source.update({"format": 2, "image_id": image_id, "archive_sha256": file_hash(archive),
                   "health_sha256": file_hash(pathlib.Path(output).parent / "health.sh"),
                   "remote_sha256": file_hash(pathlib.Path(__file__).with_name('remote_deploy.py')),
                   "deployment_sha256": file_hash(__file__),
                   'image_validation_sha256': file_hash(proof_path)})
    validate_manifest(source, source['source_sha'], source['run_id'], source['run_attempt'], source['controller_sha'])
    pathlib.Path(output).write_text(json.dumps(source, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("preflight")
    p.add_argument("--output", type=pathlib.Path, required=True)
    p = commands.add_parser("health")
    p.add_argument("--updater", required=True)
    p.add_argument("--output", required=True)
    p = commands.add_parser('tests')
    p.add_argument('--directory', required=True)
    p = commands.add_parser('artifact')
    p.add_argument('--id', type=int, required=True)
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
    elif args.command == 'manifest':
        manifest(args.preflight, args.archive, args.image_tag, args.output)
    elif args.command == 'tests':
        print(json.dumps(verify_tests(args.directory)))
    else:
        verify_artifact(api(f'/actions/artifacts/{positive_integer(args.id)}'), args.id,
                        positive_integer(os.environ['GITHUB_RUN_ID']),
                        positive_integer(os.environ['GITHUB_RUN_ATTEMPT']), sha(os.environ['GITHUB_SHA']))
