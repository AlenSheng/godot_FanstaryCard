"""Validate public evidence bytes and reject credentials before any archive write."""
import hashlib
import json
from pathlib import Path
import re

MAX_FILE_BYTES=64*1024**2
SENSITIVE_KEYS={'token','accesstoken','refreshtoken','authorization','password','secret','clientsecret','apikey','privatekey','connectionstring','ticketbody'}
SECRET_TEXT=re.compile(r'(?i)\bbearer\s+[a-z0-9_.+/=-]{8,}|\b(?:password|client_secret|api_key)\s*=\s*[^;\s\"\']{4,}')


def inspect_public(path):
    """Return only public metadata; never include rejected values in errors."""
    if path.stat().st_size>MAX_FILE_BYTES: raise ValueError('Public evidence file exceeds bounded size')
    if path.suffix.lower() not in {'.json','.jsonl','.md','.txt','.log','.trx','.xml','.yml','.yaml'}: return
    source=path.read_text(encoding='utf-8-sig')
    if SECRET_TEXT.search(source): raise ValueError('Credential-like value in public evidence')
    def visit(value):
        if isinstance(value,dict):
            for key,item in value.items():
                normalized=re.sub(r'[^a-z0-9]','',str(key).lower())
                if normalized in SENSITIVE_KEYS and item not in (None,'',[],{}):
                    raise ValueError('Sensitive field in public evidence: '+normalized)
                visit(item)
        elif isinstance(value,list):
            for item in value: visit(item)
    if path.suffix.lower()=='.json': visit(json.loads(source))
    elif path.suffix.lower()=='.jsonl':
        for line in source.splitlines():
            if line.strip(): visit(json.loads(line))


def validated_files(root, entries):
    root=Path(root).resolve()
    if not isinstance(entries,list) or not 1<=len(entries)<=2048: raise ValueError('Bounded public manifest required')
    paths=[];seen=set();total=0
    for entry in entries:
        relative=Path(entry['path'])
        path=(root/relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(root): raise ValueError('Public path escapes root')
        if path in seen: raise ValueError('Duplicate public evidence path')
        seen.add(path)
        if (any(part in ('postgres','private-pg','server-frozen','bin','obj','runtime') for part in relative.parts)
            or path.name.startswith('.env') or path.suffix.lower() in ('.pem','.key') or 'snapshot-private' in path.name):
            raise ValueError('Private/runtime artifact in public manifest')
        if type(entry.get('bytes')) is not int or entry['bytes']<0: raise ValueError('Exact byte count required')
        if not path.is_file(): raise ValueError('Public evidence missing')
        total+=path.stat().st_size
        if total>256*1024**2: raise ValueError('Public manifest exceeds bounded size')
        if path.stat().st_size!=entry['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=entry.get('sha256'):
            raise ValueError('Evidence changed after immutable manifest')
        inspect_public(path)
        paths.append(path)
    return paths


def derived_identity(parent, derived):
    """Record source/derived hashes separately without making derivations parents."""
    return {'parent':{'path':parent.name,'bytes':parent.stat().st_size,'sha256':hashlib.sha256(parent.read_bytes()).hexdigest()},
            'derived':{'path':derived.name,'bytes':derived.stat().st_size,'sha256':hashlib.sha256(derived.read_bytes()).hexdigest()},
            'relation':'derived_from','original_overwritten':False}
