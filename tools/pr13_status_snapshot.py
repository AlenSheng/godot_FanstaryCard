"""Lossless bounded snapshots; decompression never fabricates a heartbeat."""
from collections.abc import MutableMapping
import json
import zlib

class SerializedStatusCache(MutableMapping):
    def __init__(self, *, max_snapshot_bytes=32*1024*1024):
        if type(max_snapshot_bytes) is not int or not 0<max_snapshot_bytes<=32*1024*1024:
            raise ValueError('Invalid snapshot bound')
        self.max_snapshot_bytes=max_snapshot_bytes
        self._entries={}

    def __setitem__(self,key,value):
        if not isinstance(value,dict):raise ValueError('Status snapshot must be an object')
        raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf8','surrogatepass')
        if len(raw)>self.max_snapshot_bytes:raise ValueError('Status snapshot byte bound exceeded')
        packed=zlib.compress(raw,1)
        self._entries[key]=(len(raw),packed)

    def __getitem__(self,key):
        length,packed=self._entries[key]
        if type(length) is not int or not 0<length<=self.max_snapshot_bytes:raise ValueError('Invalid snapshot size')
        try:
            decoder=zlib.decompressobj();raw=decoder.decompress(packed,length+1)
            if len(raw)!=length or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                raise ValueError('Invalid compressed snapshot')
            value=json.loads(raw.decode('utf8','surrogatepass'))
        except (zlib.error,UnicodeError,TypeError) as exc:
            raise ValueError('Invalid compressed snapshot') from exc
        if not isinstance(value,dict):raise ValueError('Invalid decoded snapshot')
        return value

    def __delitem__(self,key):del self._entries[key]
    def __iter__(self):return iter(self._entries)
    def __len__(self):return len(self._entries)

    @property
    def retained_bytes(self):return sum(len(row[1]) for row in self._entries.values())

    @property
    def decoded_snapshot_bytes(self):return sum(row[0] for row in self._entries.values())
