"""Lossless, bounded compressed storage for actual native encounter evidence."""
import gzip
import hashlib
import json
from pathlib import Path

MAX_RAW_BYTES = 512 * 1024 * 1024


def digest_stream(stream):
    digest = hashlib.sha256(); size = 0
    for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
        size += len(block)
        if size > MAX_RAW_BYTES:
            raise ValueError('Native raw evidence exceeds declared storage bound')
        digest.update(block)
    return digest.hexdigest(), size


def raw_input(directory, summary):
    directory = Path(directory); plain = directory / 'encounters.jsonl'; compressed = directory / 'encounters.jsonl.gz'
    storage = summary.get('RawStorage')
    if plain.exists():
        if plain.is_symlink() or compressed.exists() or storage:
            raise ValueError('Ambiguous or redirected raw evidence')
        with plain.open('rb') as stream: digest, size = digest_stream(stream)
        if digest != summary['RawSha256']: raise ValueError('Raw digest differs')
        return plain, False, size
    if (not isinstance(storage, dict) or storage.get('format') != 'gzip'
            or storage.get('file') != 'encounters.jsonl.gz' or not compressed.is_file() or compressed.is_symlink()
            or type(storage.get('uncompressed_bytes')) is not int or not 0 < storage['uncompressed_bytes'] <= MAX_RAW_BYTES):
        raise ValueError('Declared compressed native raw evidence required')
    if compressed.stat().st_size != storage.get('stored_bytes'):
        raise ValueError('Compressed byte count differs')
    with compressed.open('rb') as stream: stored_digest, _ = digest_stream(stream)
    if stored_digest != storage.get('stored_sha256'): raise ValueError('Compressed digest differs')
    try:
        with gzip.open(compressed, 'rb') as stream: digest, size = digest_stream(stream)
    except (OSError, EOFError) as error:
        raise ValueError('Invalid or truncated compressed native evidence') from error
    if size != storage['uncompressed_bytes'] or digest != summary['RawSha256']:
        raise ValueError('Decompressed raw digest or byte count differs')
    return compressed, True, size


def open_raw(path, compressed):
    return gzip.open(path, 'rt', encoding='utf8') if compressed else path.open(encoding='utf8')


def compress_raw(directory):
    """Verify before replacing only the caller-owned original encounter file."""
    directory = Path(directory); summary_path = directory / 'summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf8'))
    raw, compressed, size = raw_input(directory, summary)
    if compressed: raise ValueError('Immutable native evidence already compressed')
    target = directory / 'encounters.jsonl.gz'
    with raw.open('rb') as source, target.open('xb') as file:
        with gzip.GzipFile(filename='', mode='wb', fileobj=file, compresslevel=1, mtime=0) as stream:
            for block in iter(lambda: source.read(4 * 1024 * 1024), b''): stream.write(block)
    with target.open('rb') as stream: stored_digest, stored_size = digest_stream(stream)
    storage = {'format': 'gzip', 'file': target.name, 'stored_bytes': stored_size, 'stored_sha256': stored_digest, 'uncompressed_bytes': size}
    with gzip.open(target, 'rb') as stream: digest, decoded_size = digest_stream(stream)
    if digest != summary['RawSha256'] or decoded_size != size:
        raise ValueError('Compression did not preserve actual native raw bytes')
    original = directory / 'summary.native.json'
    with original.open('xb') as stream: stream.write(summary_path.read_bytes())
    summary['RawStorage'] = storage
    summary_path.write_bytes((json.dumps(summary, ensure_ascii=False, indent=2) + '\n').encode())
    raw.unlink()
    raw_input(directory, summary)
    return storage
