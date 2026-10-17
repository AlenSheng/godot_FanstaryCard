"""Bounded owned audit archives and replayable disk spool; no network calls."""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

RECORD_LIMIT_BYTES = 64 * 1024
SEGMENT_LIMIT_BYTES = 16 * 1024 * 1024
MAX_SEGMENTS = 8
LEGACY_FILE_LIMIT_BYTES = SEGMENT_LIMIT_BYTES * MAX_SEGMENTS
SPOOL_LIMIT_BYTES = 2 * 1024**3
SPOOL_LIMIT_RECORDS = 2_000_000
MAX_DIAGNOSTICS = 256


class AuditLimitError(ValueError):
    pass


class OwnedAuditEvents:
    """Only the archive verifier appends ownership/sequence-qualified raw rows.

    Consumers may replay this stream without retaining every decoded payload.
    The private spool is discarded after both end-of-run analyses; original
    client archive segments are never overwritten or deleted by this module.
    """
    _owned_audit_stream_version = 1

    def __init__(self, *, max_bytes=SPOOL_LIMIT_BYTES, max_records=SPOOL_LIMIT_RECORDS):
        if type(max_bytes) is not int or not 0 < max_bytes <= SPOOL_LIMIT_BYTES:
            raise ValueError('Invalid audit spool byte bound')
        if type(max_records) is not int or not 0 < max_records <= SPOOL_LIMIT_RECORDS:
            raise ValueError('Invalid audit spool record bound')
        self._temporary = tempfile.TemporaryDirectory(prefix='pr13-owned-audit-')
        self.path = Path(self._temporary.name) / 'validated.jsonl'
        self._writer = self.path.open('xb')
        self.max_bytes, self.max_records = max_bytes, max_records
        self.total_bytes = self.count = 0
        self.closed = False
        self._hash = hashlib.sha256()
        self._digest = None
        self._next_disk_check = 0

    def append(self, raw):
        if self._writer is None or self.closed:
            raise ValueError('Audit spool is sealed')
        if len(raw) > RECORD_LIMIT_BYTES:
            raise AuditLimitError('audit_record_size_limit')
        if self.count >= self.max_records:
            raise AuditLimitError('audit_spool_record_limit')
        if self.total_bytes + len(raw) > self.max_bytes:
            raise AuditLimitError('audit_spool_byte_limit')
        if self.total_bytes >= self._next_disk_check:
            usage = shutil.disk_usage(self.path.parent)
            if usage.free < usage.total * .05 + SEGMENT_LIMIT_BYTES:
                raise AuditLimitError('audit_spool_disk_floor')
            self._next_disk_check = self.total_bytes + SEGMENT_LIMIT_BYTES
        self._writer.write(raw)
        self._hash.update(raw)
        self.total_bytes += len(raw)
        self.count += 1

    def seal(self):
        if self._writer is not None:
            self._writer.flush()
            self._writer.close()
            self._writer = None
        self._digest = self._hash.digest()

    def __len__(self):
        return self.count

    def __iter__(self):
        if self.closed or self._writer is not None:
            raise ValueError('Audit spool is unavailable or unsealed')
        digest = hashlib.sha256()
        count = size = 0
        with self.path.open('rb') as source:
            while raw := source.readline(RECORD_LIMIT_BYTES + 1):
                count += 1
                size += len(raw)
                if len(raw) > RECORD_LIMIT_BYTES or count > self.count or size > self.total_bytes:
                    raise ValueError('Validated audit spool changed')
                digest.update(raw)
                yield json.loads(raw)
        if count != self.count or size != self.total_bytes or digest.digest() != self._digest:
            raise ValueError('Validated audit spool changed')

    def close(self):
        if not self.closed:
            if self._writer is not None:
                self._writer.close()
                self._writer = None
            self._temporary.cleanup()
            self.closed = True

    def __del__(self):
        # Explicit close in the coordinator is authoritative. This also covers
        # an exception in an external caller before it takes ownership.
        if hasattr(self, 'closed') and not self.closed:
            self.close()


def _integer(value):
    return type(value) is int and value >= 0


def validate_storage(value):
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1:
        return False
    if any(not _integer(value.get(k)) for k in
           ('record_limit_bytes', 'segment_limit_bytes', 'max_segments', 'segment_count',
            'bytes_written', 'events_written', 'buffer_count', 'buffer_serialized_bytes')):
        return False
    sizes = value.get('segment_bytes')
    return (0 < value['record_limit_bytes'] <= RECORD_LIMIT_BYTES
            and 0 < value['segment_limit_bytes'] <= SEGMENT_LIMIT_BYTES
            and 0 < value['max_segments'] <= MAX_SEGMENTS
            and 0 <= value['segment_count'] <= value['max_segments']
            and isinstance(sizes, list) and len(sizes) == value['segment_count']
            and all(_integer(n) and n <= value['segment_limit_bytes'] for n in sizes)
            and sum(sizes) == value['bytes_written']
            and value['buffer_count'] == 0 and value['buffer_serialized_bytes'] == 0)


def read_owned_audits(processes, final_clients, *, max_bytes=SPOOL_LIMIT_BYTES,
                      max_records=SPOOL_LIMIT_RECORDS):
    """Bound every file/line/read/diagnostic; validate all rows before replay.

    Missing metadata is the explicit historical single-file contract. New
    segmented archives must publish exact bounded sizes and final watermarks.
    """
    events, errors = None, []
    counts = Counter()

    def error(cid, reason, **fields):
        counts[reason] += 1
        if len(errors) < MAX_DIAGNOSTICS:
            errors.append(dict(client_id=cid, error=reason, **fields))

    try:
        events = OwnedAuditEvents(max_bytes=max_bytes, max_records=max_records)
    except OSError as exc:
        return [], [dict(error='audit_spool_unavailable', exception=type(exc).__name__)]
    final_by_id = {row['client_id']: row for row in final_clients}
    exhausted = False
    try:
        for entry in processes:
            cid = entry['client_id']
            expected = 1
            final = final_by_id.get(cid, {})
            metadata = final.get('audit_storage')
            segmented = metadata is not None
            valid_metadata = validate_storage(metadata) if segmented else False
            if segmented and not valid_metadata:
                error(cid, 'audit_storage_invalid')
            declared = metadata['segment_count'] if valid_metadata else 1
            file_limit = metadata['segment_limit_bytes'] if valid_metadata else LEGACY_FILE_LIMIT_BYTES
            line_limit = metadata['record_limit_bytes'] if valid_metadata else RECORD_LIMIT_BYTES
            base = str(entry['report']) + '.telemetry'
            paths = [Path(base + ('' if i == 0 else '.' + str(i)) + '.jsonl') for i in range(MAX_SEGMENTS + 1)]
            observed_bytes = written = 0
            for path in paths[declared:]:
                if path.exists():
                    error(cid, 'unexpected_audit_segment', segment=paths.index(path))
            for segment, path in enumerate(paths[:declared]):
                if exhausted:
                    break
                try:
                    size = path.stat().st_size
                    if path.is_symlink() or not path.is_file():
                        error(cid, 'invalid_audit_segment', segment=segment)
                        continue
                    if size > file_limit:
                        error(cid, 'audit_segment_size_limit', segment=segment, bytes=size)
                        continue
                    if valid_metadata and size != metadata['segment_bytes'][segment]:
                        error(cid, 'audit_segment_size_mismatch', segment=segment)
                    consumed = line_number = 0
                    with path.open('rb') as source:
                        while raw := source.readline(line_limit + 1):
                            consumed += len(raw)
                            line_number += 1
                            if consumed > file_limit or len(raw) > line_limit:
                                error(cid, 'audit_record_or_segment_size_limit', segment=segment, line=line_number)
                                break
                            try:
                                row = json.loads(raw)
                            except (ValueError, UnicodeError, RecursionError):
                                error(cid, 'invalid_json', segment=segment, line=line_number)
                                continue
                            if not isinstance(row, dict) or any(row.get(k) != entry.get(k)
                                    for k in ('run_id', 'client_id', 'process_epoch')):
                                error(cid, 'foreign_event_context', segment=segment, line=line_number)
                                continue
                            seq = row.get('event_seq')
                            if type(seq) is not int or seq < 1:
                                error(cid, 'invalid_event_sequence', segment=segment, line=line_number)
                                continue
                            if seq != expected:
                                error(cid, 'event_sequence_gap_or_reorder', expected=expected, actual=seq)
                            if seq < expected:
                                continue
                            expected = seq + 1
                            try:
                                events.append(raw if raw.endswith(b'\n') else raw + b'\n')
                            except (AuditLimitError, OSError) as exc:
                                error(cid, str(exc) if isinstance(exc, AuditLimitError) else 'audit_spool_write_failed')
                                exhausted = True
                                break
                            written += 1
                    observed_bytes += consumed
                except (OSError, UnicodeError) as exc:
                    error(cid, type(exc).__name__, segment=segment)
            maximum = final.get('event_seq_max')
            if not _integer(maximum) or maximum != expected - 1:
                error(cid, 'final_audit_watermark_mismatch', final_event_seq_max=maximum,
                      audit_event_seq_max=expected - 1)
            if valid_metadata and (observed_bytes != metadata['bytes_written'] or written != metadata['events_written']):
                error(cid, 'audit_storage_totals_mismatch', actual_bytes=observed_bytes, actual_events=written)
        events.seal()
    except (OSError, ValueError, RecursionError) as exc:
        error('', 'audit_spool_finalize_failed', exception=type(exc).__name__)
        try:
            events.close()
        except OSError as cleanup:
            error('', 'audit_spool_cleanup_failed', exception=type(cleanup).__name__)
        events = []
    except BaseException:
        events.close()
        raise
    if sum(counts.values()) > len(errors):
        errors.append(dict(error='audit_diagnostics_truncated', total_errors=sum(counts.values()),
                           retained_diagnostics=len(errors), counts_by_error=dict(counts)))
    return events, errors
