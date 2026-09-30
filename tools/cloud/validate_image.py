"""Run the existing validator against final image DLLs, with private evidence local."""
import argparse
import importlib.util
import json
import pathlib
import sys
from deployment import sha, validate_image_proof


def validate(source, image, builder, source_sha, output):
    source = pathlib.Path(source).resolve(strict=True)
    sha(source_sha)
    # Never inspect a real release key. Check existence only and stop safely.
    if (source / 'release-encryption.key').exists():
        raise ValueError('Image validation requires a credential-free source checkout')
    trusted_tools = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(trusted_tools))
    spec = importlib.util.spec_from_file_location('trusted_image_validator', trusted_tools / 'validate_docker_server.py')
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    validator.ROOT = source
    validator.PRIVATE = output.parent / 'private-image-validation'
    # Disposable fixture value, never a server credential or uploaded secret.
    validator.secrets.token_hex = lambda count: '0' * (count * 2)
    validator.PRIVATE.mkdir(parents=True, exist_ok=True)
    before = set(validator.PRIVATE.iterdir())
    ok = validator.validate(image, builder)
    created = set(validator.PRIVATE.iterdir()) - before
    if len(created) != 1:
        raise ValueError('Ambiguous final-image evidence')
    report = json.loads((created.pop() / 'verification.json').read_text())
    proof = {'ok': ok, 'source_sha': source_sha, 'image_id': report.get('image'),
             'assemblies': report.get('assemblies'), 'tests': report.get('tests'),
             'runtime_uid': report.get('runtime_uid'),
             'restart_test_passed': report.get('smoke_before', {}).get('ok') is True and report.get('smoke_after', {}).get('ok') is True,
             'database_outage': report.get('database_outage'),
             'production_local_auth_status': report.get('production_local_auth_status'),
             'cleanup_ok': report.get('cleanup', {}).get('ok') is True}
    output.write_text(json.dumps(proof, indent=2) + '\n')
    if not ok:
        raise ValueError('Final-image validation failed; private local evidence retained')
    validate_image_proof(proof, proof['image_id'], source_sha)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--builder', required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    validate(args.source, args.image, args.builder, args.source_sha, args.output)
