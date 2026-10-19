"""Validate public evidence snapshots and reject credentials before archive writes."""
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import stat

MAX_FILE_BYTES = 64 * 1024**2
MAX_TOTAL_BYTES = 256 * 1024**2
TEXT_SUFFIXES = {'.json', '.jsonl', '.md', '.txt', '.log', '.trx', '.xml', '.yml', '.yaml'}
SENSITIVE_KEYS = {'token', 'accesstoken', 'refreshtoken', 'authorization',
                  'proxyauthorization', 'password', 'pwd', 'secret', 'clientsecret',
                  'apikey', 'privatekey', 'connectionstring', 'ticketbody'}
SECRET_TEXT = re.compile(r'(?i)\bbearer\s+[a-z0-9_.+/=-]{8,}')
PRIVATE_BLOCK = re.compile(r'-----BEGIN (?P<kind>(?:[A-Z0-9]+ )*PRIVATE KEY)-----(?P<body>.*?)-----END (?P=kind)-----', re.S)
BASIC_HEADER = re.compile(r'(?i)\b(?:proxy-)?authorization[ \t]*[:=][ \t]*basic[ \t]+([a-z0-9+/=_-]{8,})')
CREDENTIAL_URI = re.compile(r'(?i)\b[a-z][a-z0-9+.-]*://[^\s/@:]+:(?P<password>[^\s/@]+)@')
ASSIGNMENT = re.compile(r'''(?im)(?:^|[;\r\n]|\b)(?<![a-z0-9_/-])[ \t]*(?:-[ \t]+)?["']?(?:token|access[_-]?token|refresh[_-]?token|password|pwd|secret|client[_-]?secret|api[_-]?key|private[_-]?key|connection[_-]?string)["']?[ \t]*[:=][ \t]*([^\r\n;]+)''')
REFERENCE = re.compile(r'^(?:\$\{\{.*\}\}|\$\{[^}]+\}|\$env:[a-z_]\w*|%[a-z_]\w*%)$', re.I)


def _reference(value):
    value = value.strip().strip('"\'').strip()
    return value.lower() in {'null', 'none', '~', '<redacted>', '<masked>', '<from-env>', '***'} or bool(REFERENCE.fullmatch(value))


def _sensitive_text(source, assignments=True):
    if SECRET_TEXT.search(source):
        return True
    for block in PRIVATE_BLOCK.finditer(source):
        if any(re.fullmatch(r'[A-Za-z0-9+/=]{32,}', line.strip())
               for line in block.group('body').splitlines()):
            return True
    for header in BASIC_HEADER.finditer(source):
        try:
            encoded = header.group(1)
            decoded = base64.b64decode(encoded + '=' * (-len(encoded) % 4),
                                       altchars=b'-_', validate=True)
        except (ValueError, binascii.Error):
            continue
        if b':' in decoded and decoded.split(b':', 1)[1]:
            return True
    if any(not _reference(match.group('password')) for match in CREDENTIAL_URI.finditer(source)):
        return True
    if assignments:
        for match in ASSIGNMENT.finditer(source):
            value = match.group(1).strip().strip('"\'').strip()
            if not value or _reference(value):
                continue
            # sudo's PWD field is the working directory, not a database password.
            # Ignore only that exact field in a complete sudo audit prefix;
            # assignments in COMMAND, including PWD, are still inspected.
            line_start = source.rfind('\n', 0, match.start()) + 1
            prefix = re.match(r'[ \t]*[A-Za-z0-9_.-]+[ \t]*:[ \t]+PWD=(?P<directory>/[^;\r\n]*);[ \t]*USER=[A-Za-z0-9_.-]+[ \t]*;[ \t]*COMMAND=', source[line_start:])
            if prefix and match.start(1) == line_start + prefix.start('directory'):
                continue
            return True
    return False


def inspect_public_bytes(path, payload):
    """Inspect the exact captured bytes; errors never include rejected values."""
    path = Path(path)
    if len(payload) > MAX_FILE_BYTES:
        raise ValueError('Public evidence file exceeds bounded size')
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return
    try:
        source = payload.decode('utf-8-sig')
    except UnicodeError:
        raise ValueError('Public evidence text is not UTF-8') from None
    if _sensitive_text(source, assignments=path.suffix.lower() not in {'.json', '.jsonl'}):
        raise ValueError('Credential-like value in public evidence')

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = re.sub(r'[^a-z0-9]', '', str(key).lower())
                if (normalized in SENSITIVE_KEYS and item not in (None, '', [], {})
                        and not (isinstance(item, str) and _reference(item))):
                    raise ValueError('Sensitive field in public evidence: ' + normalized)
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, str) and _sensitive_text(value):
            raise ValueError('Credential-like value in public evidence')

    try:
        if path.suffix.lower() == '.json':
            visit(json.loads(source))
        elif path.suffix.lower() == '.jsonl':
            for line in source.splitlines():
                if line.strip():
                    visit(json.loads(line))
    except json.JSONDecodeError:
        raise ValueError('Malformed public evidence JSON') from None


def public_payload(path):
    """Capture one bounded stable payload for validation and subsequent writing."""
    path = Path(path)
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise ValueError('Public evidence must be a regular file')
    if before.st_size > MAX_FILE_BYTES:
        raise ValueError('Public evidence file exceeds bounded size')
    def identity(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if identity(before) != identity(opened):
            raise ValueError('Evidence changed before reading public snapshot')
        payload = stream.read(MAX_FILE_BYTES + 1)
        after_read = os.fstat(stream.fileno())
    after = path.stat(follow_symlinks=False)
    if identity(before) != identity(after_read) or identity(before) != identity(after):
        raise ValueError('Evidence changed while reading public snapshot')
    inspect_public_bytes(path, payload)
    return payload


def inspect_public(path):
    """Return only public metadata; never include rejected values in errors."""
    public_payload(path)


def validated_payloads(root, entries):
    """Return immutable (path, bytes) snapshots, not paths to be read again."""
    root = Path(root).resolve()
    if not isinstance(entries, list) or not 1 <= len(entries) <= 2048:
        raise ValueError('Bounded public manifest required')
    payloads = []
    seen = set()
    total = 0
    for entry in entries:
        relative = Path(entry['path'])
        path = (root / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(root):
            raise ValueError('Public path escapes root')
        if path in seen:
            raise ValueError('Duplicate public evidence path')
        seen.add(path)
        parts = {part.lower() for part in relative.parts}
        if (parts.intersection({'postgres', 'private-pg', 'server-frozen', 'bin', 'obj', 'runtime'})
                or path.name.lower().startswith('.env') or path.suffix.lower() in ('.pem', '.key')
                or 'snapshot-private' in path.name.lower()):
            raise ValueError('Private/runtime artifact in public manifest')
        if type(entry.get('bytes')) is not int or entry['bytes'] < 0:
            raise ValueError('Exact byte count required')
        if not path.is_file():
            raise ValueError('Public evidence missing')
        total += path.stat().st_size
        if total > MAX_TOTAL_BYTES:
            raise ValueError('Public manifest exceeds bounded size')
        payload = public_payload(path)
        if len(payload) != entry['bytes'] or hashlib.sha256(payload).hexdigest() != entry.get('sha256'):
            raise ValueError('Evidence changed after immutable manifest')
        payloads.append((path, payload))
    return payloads


def validated_files(root, entries):
    """Compatibility API for readers; exporters must use validated_payloads."""
    return [path for path, payload in validated_payloads(root, entries)]


def derived_identity(parent, derived):
    """Record distinct original/derived objects without hiding file aliases."""
    parent, derived = Path(parent), Path(derived)
    if parent.resolve() == derived.resolve() or parent.samefile(derived):
        raise ValueError('Original and derived evidence must be distinct files')
    return {'parent': {'path': parent.name, 'bytes': parent.stat().st_size,
                       'sha256': hashlib.sha256(parent.read_bytes()).hexdigest()},
            'derived': {'path': derived.name, 'bytes': derived.stat().st_size,
                        'sha256': hashlib.sha256(derived.read_bytes()).hexdigest()},
            'relation': 'derived_from', 'original_overwritten': False}
