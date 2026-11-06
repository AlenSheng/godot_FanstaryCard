"""Lossless transport only: every decoded member must match the full payload SHA."""
import hashlib,struct,zlib

MAGIC=b'FCBDZ1\0\0'
BLOCK=16384
BACK=8192
MAX_FILE=64*1024**2

def encode(base,target):
    assert len(target)<=MAX_FILE
    result=bytearray(MAGIC+hashlib.sha256(base).digest()+struct.pack('!QII',len(target),BLOCK,BACK))
    for offset in range(0,len(target),BLOCK):
        dictionary=base[max(0,offset-BACK):offset+BLOCK+BACK]
        compressor=zlib.compressobj(9,zlib.DEFLATED,zlib.MAX_WBITS,zdict=dictionary) if dictionary else zlib.compressobj(9)
        compressed=compressor.compress(target[offset:offset+BLOCK])+compressor.flush()
        result.extend(struct.pack('!I',len(compressed)));result.extend(compressed)
    return bytes(result)

def decode(base,patch):
    if len(patch)<56 or patch[:8]!=MAGIC or patch[8:40]!=hashlib.sha256(base).digest():raise ValueError('Binary transport base or header differs.')
    length,block,back=struct.unpack('!QII',patch[40:56])
    if length>MAX_FILE or block!=BLOCK or back!=BACK:raise ValueError('Binary transport bounds differ.')
    position=56;result=bytearray()
    for offset in range(0,length,block):
        if position+4>len(patch):raise ValueError('Truncated binary transport length.')
        size=struct.unpack('!I',patch[position:position+4])[0];position+=4
        if size>BLOCK+1024 or position+size>len(patch):raise ValueError('Binary transport block is outside its bounds.')
        dictionary=base[max(0,offset-BACK):offset+block+back]
        decompressor=zlib.decompressobj(zdict=dictionary) if dictionary else zlib.decompressobj()
        expected=min(block,length-offset)
        value=decompressor.decompress(patch[position:position+size],expected+1);position+=size
        if len(value)!=expected or not decompressor.eof or decompressor.unconsumed_tail or decompressor.unused_data:
            raise ValueError('Binary transport block did not decode exactly.')
        result.extend(value)
    if position!=len(patch) or len(result)!=length:raise ValueError('Binary transport has trailing or missing data.')
    return bytes(result)
