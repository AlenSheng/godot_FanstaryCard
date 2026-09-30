"""Stage only named Godot CI reports; never walk runtime or credential trees."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat


HTTP_FIXTURE = tuple('http-fixture/' + name for name in
                     ('results.json', 'import.log', 'codec.log', 'transport.log'))
PROFILES = {
    'cloud-local': ('source.txt', 'dotnet.txt', 'godot.txt', 'postgres.txt',
                    'domain.trx', 'postgres.trx', 'test-counts.json',
                    'cloud-tests.log', 'godot-fixture.log', 'local-integration.json') + HTTP_FIXTURE,
    'gameplay-client': ('godot-version.txt', 'import.log', 'load-parse.log',
                        'client.log', 'lobby-race.log', 'http-boundary/boundary.log',
                        'http-boundary/result.json', 'offline-cases/cases.jsonl',
                        'offline-cases/report.json') + HTTP_FIXTURE,
    'numerical-client': ('version.txt', 'import.log', 'numerics.log',
                         'preview-parity/input.json', 'preview-parity/results.json',
                         'preview-parity/manifest.json', 'preview-parity/server.log',
                         'preview-parity/client.log'),
}


def scrub(value):
    value = re.sub(r'-----BEGIN [^\r\n]*PRIVATE KEY-----.*?-----END [^\r\n]*PRIVATE KEY-----',
                   '[redacted private key block]', value, flags=re.S)
    value = re.sub(r'(?i)Bearer\s+[^\s"<>]+', 'Bearer [redacted]', value)
    value = re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b', '[redacted JWT]', value)
    return re.sub(r'(?im)^.*(?:TEST_SERVER_SSH_KEY|GH_TOKEN|accessToken|access_token|api[_-]?key|password)\s*["\']?\s*[:=].*$',
                  '[redacted credential assignment]', value)


def read_report(root_fd, relative):
    """Open relative to pinned directory descriptors; reject links and devices."""
    parts = Path(relative).parts
    directory = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('Report must be a regular file with one link')
            return stream.read().decode('utf-8', errors='replace')
    finally:
        os.close(directory)


def export(source, destination, profile):
    source, destination = source.absolute(), destination.absolute()
    if any(c in str(path) for path in (source, destination) for c in ('\r', '\n')):
        raise ValueError('Evidence paths cannot contain line breaks')
    if source.resolve() != source or destination.parent.resolve() != destination.parent:
        raise ValueError('Evidence roots cannot have symlinked ancestors')
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Evidence staging must be separate from its source')
    # All three callers are Linux CI jobs. Fail closed on platforms lacking
    # descriptor-relative, no-follow file access instead of following symlinks.
    if not all(hasattr(os, flag) for flag in ('O_NOFOLLOW', 'O_DIRECTORY')):
        raise ValueError('Evidence export requires no-follow directory access')
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    inventory = {'profile': profile, 'files': [], 'missing': [], 'rejected': []}
    root_fd = None
    try:
        try:
            root_fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except FileNotFoundError:
            inventory['missing'] = list(PROFILES[profile])
        except OSError as error:
            inventory['rejected'].append({'name': '.', 'error': type(error).__name__})
        if root_fd is not None:
            for relative in PROFILES[profile]:
                try:
                    value = scrub(read_report(root_fd, relative)).encode('utf-8')
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open('xb') as stream:
                        stream.write(value)
                    inventory['files'].append({'name': relative, 'bytes': len(value),
                                               'sha256': hashlib.sha256(value).hexdigest()})
                except FileNotFoundError:
                    inventory['missing'].append(relative)
                except (OSError, ValueError) as error:
                    # Report only the fixed relative name and error class; do
                    # not disclose a link target or accidentally printed data.
                    inventory['rejected'].append({'name': relative, 'error': type(error).__name__})
    finally:
        if root_fd is not None:
            os.close(root_fd)
        (destination / 'evidence-inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
    return inventory


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=PROFILES, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    result = export(args.source, args.destination, args.profile)
    # Emit an upload location only after this process created a fresh staging
    # directory. A pre-existing destination must never be uploaded on failure.
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with open(output, 'a', encoding='utf-8') as stream:
            stream.write('artifact_directory=' + str(args.destination.absolute()) + '\n')
    print(json.dumps({'profile': args.profile, 'exported': len(result['files']),
                      'missing': len(result['missing']), 'rejected': len(result['rejected'])}))
    raise SystemExit(1 if result['rejected'] else 0)
