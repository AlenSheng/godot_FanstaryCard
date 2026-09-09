#!/usr/bin/env python3
"""Write a Photoshop PSD that CC 2018 (and CS6+) can open.

pytoshop's ZIP-compressed files are rejected by CC 2018 as
"not compatible with this version". This writer uses the classic
PSD v1 layout: 8-bit RGB, PackBits RLE, a real merged composite,
global layer-mask length 0, and Version Info file_version=1.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np


def _u8(n: int) -> bytes:
    return struct.pack(">B", n)


def _u16(n: int) -> bytes:
    return struct.pack(">H", n)


def _i16(n: int) -> bytes:
    return struct.pack(">h", n)


def _u32(n: int) -> bytes:
    return struct.pack(">I", n)


def _i32(n: int) -> bytes:
    return struct.pack(">i", n)


def _pad(data: bytes, multiple: int) -> bytes:
    extra = (-len(data)) % multiple
    return data + (b"\x00" * extra)


def _pascal4(name: str) -> bytes:
    raw = name.encode("ascii", "replace")[:255]
    return _pad(_u8(len(raw)) + raw, 4)


def _unicode_psd(text: str, terminate: bool = False) -> bytes:
    chars = text + ("\x00" if terminate else "")
    encoded = chars.encode("utf-16-be")
    return _u32(len(chars)) + encoded


def packbits_row(row: np.ndarray) -> bytes:
    data = np.ascontiguousarray(row, dtype=np.uint8).tobytes()
    n = len(data)
    out = bytearray()
    i = 0
    while i < n:
        run = 1
        while i + run < n and run < 128 and data[i] == data[i + run]:
            run += 1
        if run >= 3:
            out.append((257 - run) & 0xFF)
            out.append(data[i])
            i += run
            continue
        start = i
        i += run
        while i < n and (i - start) < 128:
            run = 1
            while i + run < n and run < 128 and data[i] == data[i + run]:
                run += 1
            if run >= 3:
                break
            i += run
        lit = i - start
        out.append(lit - 1)
        out.extend(data[start:i])
    return bytes(out)


def encode_rle_channel(plane: np.ndarray) -> bytes:
    rows = [packbits_row(plane[y]) for y in range(plane.shape[0])]
    table = b"".join(_u16(len(r)) for r in rows)
    return _u16(1) + table + b"".join(rows)


def encode_raw_channel(plane: np.ndarray) -> bytes:
    return _u16(0) + np.ascontiguousarray(plane, dtype=np.uint8).tobytes()


def encode_channel(plane: np.ndarray) -> bytes:
    rle = encode_rle_channel(plane)
    raw = encode_raw_channel(plane)
    return rle if len(rle) <= len(raw) else raw


def _tagged(key: bytes, payload: bytes) -> bytes:
    if len(key) != 4:
        raise ValueError("tagged key must be 4 bytes")
    padded = _pad(payload, 2)
    return b"8BIM" + key + _u32(len(payload)) + padded


def _lsct(kind: int, blend: bytes = b"norm") -> bytes:
    # 1=open folder, 2=closed folder, 3=hidden bounding divider
    if kind == 3:
        return _tagged(b"lsct", _u32(3))
    return _tagged(b"lsct", _u32(kind) + b"8BIM" + blend)


def _luni_name(name: str) -> bytes:
    return _tagged(b"luni", _unicode_psd(name))


def _lyid(layer_id: int) -> bytes:
    return _tagged(b"lyid", _u32(layer_id))


def _lclr(color: int) -> bytes:
    color = max(0, min(7, int(color)))
    return _tagged(b"lclr", _u16(color) + _u16(0) * 3)


def _resource(res_id: int, payload: bytes, name: str = "") -> bytes:
    name_bytes = name.encode("ascii", "replace")[:255]
    header = b"8BIM" + _u16(res_id) + _pascal_odd(name_bytes)
    return header + _u32(len(payload)) + _pad(payload, 2)


def _pascal_odd(raw: bytes) -> bytes:
    # Pascal string padded to even including the length byte.
    return _pad(_u8(len(raw)) + raw, 2)


def _resolution_info(dpi: int = 72) -> bytes:
    # 16.16 fixed point
    fixed = dpi << 16
    # hRes, hResUnit=1 inch, widthUnit=1 inch, vRes, vResUnit, heightUnit
    return _resource(1005, struct.pack(">IHH IHH", fixed, 1, 1, fixed, 1, 1))


def _version_info() -> bytes:
    # Keep file_version=1 so CC 2018 (and CS6) accept the document.
    payload = (
        _u32(1)
        + _u8(1)  # has real merged data
        + _unicode_psd("Adobe Photoshop", terminate=True)
        + _unicode_psd("Adobe Photoshop", terminate=True)
        + _u32(1)
    )
    return _resource(1057, payload)


@dataclass
class PsdLayer:
    name: str
    visible: bool = True
    opacity: int = 255
    blend: bytes = b"norm"
    color: int = 0
    # image layers
    rgba: Optional[np.ndarray] = None
    left: int = 0
    top: int = 0
    # groups
    is_group: bool = False
    is_group_end: bool = False
    closed: bool = False
    children: List["PsdLayer"] = field(default_factory=list)


def _empty_channels() -> List[Tuple[int, bytes]]:
    empty = _u16(0)
    return [(-1, empty), (0, empty), (1, empty), (2, empty)]


def _image_channels(rgba: np.ndarray) -> List[Tuple[int, bytes]]:
    a = rgba[:, :, 3]
    r = rgba[:, :, 0]
    g = rgba[:, :, 1]
    b = rgba[:, :, 2]
    return [
        (-1, encode_channel(a)),
        (0, encode_channel(r)),
        (1, encode_channel(g)),
        (2, encode_channel(b)),
    ]


def _walk_file_order(layers: Sequence[PsdLayer]) -> Iterable[PsdLayer]:
    """Yield records bottom-to-top as stored in a PSD file."""
    for layer in reversed(list(layers)):
        if layer.is_group:
            yield PsdLayer(
                name="</Layer group>",
                is_group_end=True,
                visible=True,
                blend=b"norm",
            )
            yield from _walk_file_order(layer.children)
            yield PsdLayer(
                name=layer.name,
                is_group=True,
                closed=layer.closed,
                visible=layer.visible,
                color=layer.color,
                blend=b"pass",
            )
        else:
            yield layer


def _layer_record(layer: PsdLayer, layer_id: int) -> Tuple[bytes, bytes]:
    if layer.rgba is not None:
        h, w = layer.rgba.shape[:2]
        top, left = int(layer.top), int(layer.left)
        bottom, right = top + h, left + w
        channels = _image_channels(layer.rgba)
    else:
        top = left = bottom = right = 0
        channels = _empty_channels()

    flags = 0x08  # bit 3: flags 4-7 useful
    if not layer.visible:
        flags |= 0x02
    if layer.is_group or layer.is_group_end:
        flags |= 0x10  # pixel data irrelevant

    extra = _u32(0)  # no layer mask
    extra += _u32(0)  # no blending ranges
    extra += _pascal4(_ascii_name(layer.name))
    extra += _luni_name(layer.name)
    extra += _lyid(layer_id)
    extra += _lclr(layer.color)
    if layer.is_group:
        extra += _lsct(2 if layer.closed else 1, b"pass")
    elif layer.is_group_end:
        extra += _lsct(3)

    rec = bytearray()
    rec += _i32(top) + _i32(left) + _i32(bottom) + _i32(right)
    rec += _u16(len(channels))
    for cid, payload in channels:
        rec += _i16(cid) + _u32(len(payload))
    rec += b"8BIM" + layer.blend
    rec += _u8(layer.opacity)
    rec += _u8(0)  # clipping
    rec += _u8(flags)
    rec += _u8(0)
    rec += _u32(len(extra))
    rec += extra
    channel_data = b"".join(payload for _, payload in channels)
    return bytes(rec), channel_data


def _ascii_name(name: str) -> str:
    raw = name.encode("ascii", "ignore").decode("ascii").strip()
    if raw:
        return raw[:31]
    return "Layer"


def _merged_rle(rgb: np.ndarray) -> bytes:
    # rgb: HxWx3
    planes = [rgb[:, :, c] for c in range(3)]
    packed = [encode_rle_channel(p)[2:] for p in planes]  # drop per-channel compression header
    # Merged image: one compression field, then all channels' RLE tables+data concatenated
    # Each encode_rle_channel is: u16(1) + row table + rows
    # For merged PSD, compression is once at the start, then for each channel: table then data.
    body = b"".join(encode_rle_channel(p)[2:] for p in planes)
    return _u16(1) + body


def write_cc2018_psd(
    path,
    width: int,
    height: int,
    layers: Sequence[PsdLayer],
    merged_rgb: np.ndarray,
) -> None:
    records = list(_walk_file_order(layers))
    rec_bytes = []
    ch_bytes = []
    for i, layer in enumerate(records, start=1):
        rec, ch = _layer_record(layer, i)
        rec_bytes.append(rec)
        ch_bytes.append(ch)

    layer_count = len(records)
    inner = _i16(-layer_count) + b"".join(rec_bytes) + b"".join(ch_bytes)
    # Layer info length must be even.
    if len(inner) % 2:
        inner += b"\x00"
    layer_info = _u32(len(inner)) + inner
    global_mask = _u32(0)
    layer_mask_section = layer_info + global_mask

    resources = _resolution_info(72) + _version_info()

    header = (
        b"8BPS"
        + _u16(1)
        + b"\x00" * 6
        + _u16(3)
        + _u32(height)
        + _u32(width)
        + _u16(8)
        + _u16(3)
    )

    merged = np.ascontiguousarray(merged_rgb[:, :, :3], dtype=np.uint8)
    if merged.shape[0] != height or merged.shape[1] != width:
        raise ValueError("merged image must match canvas")

    blob = (
        header
        + _u32(0)
        + _u32(len(resources))
        + resources
        + _u32(len(layer_mask_section))
        + layer_mask_section
        + _merged_rle(merged)
    )
    with open(path, "wb") as fh:
        fh.write(blob)


def image_layer(name: str, rgba: np.ndarray, left: int, top: int, visible: bool = True, color: int = 0) -> PsdLayer:
    arr = np.ascontiguousarray(rgba, dtype=np.uint8)
    if arr.ndim != 3 or arr.shape[2] != 4:
        raise ValueError(f"expected HxWx4 for {name}")
    return PsdLayer(name=name, rgba=arr, left=int(left), top=int(top), visible=visible, color=color)


def group(name: str, children: List[PsdLayer], color: int = 0, closed: bool = False) -> PsdLayer:
    return PsdLayer(name=name, is_group=True, children=list(children), color=color, closed=closed)
