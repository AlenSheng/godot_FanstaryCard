#!/usr/bin/env python3
"""Build a layered, Photoshop-openable PSD from ui_action_1920x1080.

The mockup is split into named groups that match GDD §7.1 清怪后行动栏:
background, battle-end HUD, panel chrome, and one group per action button
(card surface + icon + caption, plus timer/arrow where present).

Usage:
    python3 tools/build_ui_action_psd.py

Rebuilds ``art/ui_mockups_v058/ui_action_1920x1080.psd`` from the committed
layer PNGs and ``ui_action_layer_index.json``. If ``/tmp/ui_action_keep``
source cuts are present, it re-extracts layers first.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import cv2
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from psd_cc2018 import group, image_layer, write_cc2018_psd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "art" / "ui_mockups_v058"
LAYER_DIR = OUT_DIR / "ui_action_layers"
CANVAS = (1920, 1080)

# Photoshop layer-list colors: 0 none, 1 red, 2 orange, 3 yellow, 4 green, 5 blue, 6 violet, 7 gray
COLOR_GRAY = 7
COLOR_YELLOW = 3
COLOR_BLUE = 5
COLOR_ORANGE = 2
COLOR_VIOLET = 6
COLOR_GREEN = 4


def load_rgba(path: Path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGBA"))


def overlay(dst: np.ndarray, src: np.ndarray, x: int, y: int) -> None:
    h, w = src.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, dst.shape[1]), min(y + h, dst.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    s = src[y0 - y : y1 - y, x0 - x : x1 - x].astype(np.float32) / 255.0
    d = dst[y0:y1, x0:x1].astype(np.float32) / 255.0
    a = s[:, :, 3:4]
    out = np.empty_like(d)
    out[:, :, :3] = d[:, :, :3] * (1.0 - a) + s[:, :, :3] * a
    out[:, :, 3:4] = d[:, :, 3:4] * (1.0 - a) + a
    dst[y0:y1, x0:x1] = np.clip(np.round(out * 255.0), 0, 255).astype(np.uint8)


def trim_rgba(arr: np.ndarray, origin_x: int, origin_y: int, threshold: int = 4):
    alpha = arr[:, :, 3]
    ys, xs = np.where(alpha > threshold)
    if xs.size == 0:
        return None
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    cropped = np.ascontiguousarray(arr[y0:y1, x0:x1])
    return cropped, origin_x + x0, origin_y + y0


def extract_text(orig: np.ndarray, clean: np.ndarray, bbox, pad: int = 4, kind: str = "gold"):
    """Pull caption glyphs from the mockup. kind=gold (UI copy) or cyan (timer)."""
    x0, y0, x1, y1 = bbox
    h, w = orig.shape[:2]
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(w, x1 + pad), min(h, y1 + pad)
    o = orig[y0:y1, x0:x1]
    c = clean[y0:y1, x0:x1]
    hsv = cv2.cvtColor(o[:, :, :3], cv2.COLOR_RGB2HSV)
    if kind == "cyan":
        color = (
            (hsv[:, :, 0] >= 78)
            & (hsv[:, :, 0] <= 112)
            & (hsv[:, :, 1] >= 70)
            & (hsv[:, :, 2] >= 110)
        )
    else:
        color = (
            (hsv[:, :, 0] <= 42)
            & (hsv[:, :, 1] >= 18)
            & (hsv[:, :, 1] <= 110)
            & (hsv[:, :, 2] >= 140)
        )
    core = color.astype(np.uint8)
    halo = cv2.dilate(core, np.ones((3, 3), np.uint8), iterations=1)
    diff = np.abs(o.astype(np.int16) - c.astype(np.int16)).max(axis=2).astype(np.float32)
    alpha = np.clip(halo.astype(np.float32) * np.clip(diff / 28.0, 0.0, 1.0), 0.0, 1.0)
    alpha = np.maximum(alpha, core.astype(np.float32))
    layer = o.copy()
    layer[:, :, 3] = np.clip(np.round(alpha * 255.0), 0, 255).astype(np.uint8)
    trimmed = trim_rgba(layer, x0, y0, threshold=8)
    if trimmed is None:
        raise RuntimeError(f"empty text crop {bbox}")
    return trimmed


def save_layer(path: Path, arr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(path)


def place_sprite(src_dir: Path, filename: str, bbox) -> tuple[np.ndarray, int, int]:
    arr = load_rgba(src_dir / filename)
    x0, y0, x1, y1 = bbox
    expected = (y1 - y0, x1 - x0)
    if arr.shape[0] != expected[0] or arr.shape[1] != expected[1]:
        arr = np.array(
            Image.fromarray(arr).resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS)
        )
    trimmed = trim_rgba(arr, x0, y0)
    if trimmed is None:
        raise RuntimeError(f"empty sprite {filename}")
    return trimmed


def main() -> None:
    src = Path("/tmp/ui_action_keep")
    sprite_dir = src / "sprites"
    orig = load_rgba(src / "ui_action_1920x1080.png")
    clean = load_rgba(src / "work" / "ui_action_ocr_cleaned.png")
    background = load_rgba(src / "background_dungeon.png")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if LAYER_DIR.exists():
        shutil.rmtree(LAYER_DIR)
    LAYER_DIR.mkdir(parents=True)

    shutil.copyfile(src / "ui_action_1920x1080.png", OUT_DIR / "ui_action_1920x1080.png")

    records: list[dict] = []
    packed: dict[str, tuple[np.ndarray, int, int]] = {}

    def add(key: str, name: str, arr: np.ndarray, x: int, y: int, group: str, kind: str, note: str = "") -> None:
        packed[key] = (arr, x, y)
        save_layer(LAYER_DIR / f"{key}.png", arr)
        records.append(
            {
                "id": key,
                "name": name,
                "group": group,
                "kind": kind,
                "file": f"ui_action_layers/{key}.png",
                "left": x,
                "top": y,
                "width": int(arr.shape[1]),
                "height": int(arr.shape[0]),
                "note": note,
            }
        )

    bg, bx, by = trim_rgba(background, 0, 0)
    add("00_背景_地牢场景", "地牢场景", bg, bx, by, "00_背景", "background", "UI 抠掉后的完整场景，含泉水与拱门")

    badge, x, y = place_sprite(sprite_dir, "battle_end_badge.png", [32, 22, 110, 106])
    add("01_徽章_交叉剑盾", "徽章_交叉剑盾", badge, x, y, "01_战斗结束", "badge", "左上角战斗结束纹章")
    text = extract_text(orig, clean, [112, 42, 302, 100], pad=4, kind="gold")
    add("01_文字_战斗结束", "文字_战斗结束", text[0], text[1], text[2], "01_战斗结束", "text", "可替换文案：战斗结束")

    panel, x, y = place_sprite(sprite_dir, "action_panel.png", [106, 610, 1814, 1034])
    add("02_底板_行动面板", "底板_行动面板", panel, x, y, "02_行动栏", "panel", "底栏金属外框，卡片从其上叠放")

    title, x, y = place_sprite(sprite_dir, "current_action_title_plate.png", [710, 536, 1210, 649])
    add("02_底板_标题牌", "底板_标题牌", title, x, y, "02_标题_当前格行动", "panel", "当前格行动标题牌")
    text = extract_text(orig, clean, [812, 564, 1108, 626], pad=4, kind="gold")
    add("02_文字_当前格行动", "文字_当前格行动", text[0], text[1], text[2], "02_标题_当前格行动", "text", "可替换文案：当前格行动")

    buttons = [
        {
            "id": "01",
            "group": "02_按钮_01_生命泉水",
            "label": "生命泉水",
            "card": ("action_card_01.png", [150, 638, 444, 1012], "卡面_选中橙光"),
            "icon": ("fountain_icon.png", [184, 658, 402, 864], "图标_生命泉水"),
            "title_bbox": [196, 870, 406, 922],
            "clock": ("timer_clock_01.png", [237, 941, 265, 969], "图标_读条时钟"),
            "timer_bbox": [268, 928, 385, 966],
            "arrow": None,
            "note": "本格有泉且未喝才出现；读条 1.2s；效果图为选中态",
            "color": COLOR_ORANGE,
        },
        {
            "id": "02",
            "group": "02_按钮_02_使用生命药剂",
            "label": "使用生命药剂",
            "card": ("action_card_02.png", [446, 644, 706, 1004], "卡面"),
            "icon": ("health_potion_icon.png", [496, 674, 668, 872], "图标_生命药剂"),
            "title_bbox": [472, 874, 690, 939],
            "clock": None,
            "timer_bbox": None,
            "arrow": None,
            "note": "非战斗且背包有药剂才出现",
            "color": COLOR_BLUE,
        },
        {
            "id": "03",
            "group": "02_按钮_03_玩家A遗物",
            "label": "玩家A遗物",
            "card": ("action_card_03.png", [710, 644, 970, 1004], "卡面"),
            "icon": ("player_a_relic_icon.png", [754, 666, 952, 876], "图标_头盔桂冠"),
            "title_bbox": [742, 874, 954, 939],
            "clock": None,
            "timer_bbox": None,
            "arrow": None,
            "note": "每一份遗物单独一个按钮，带死者名，禁止合成大池",
            "color": COLOR_VIOLET,
        },
        {
            "id": "04",
            "group": "02_按钮_04_玩家B遗物",
            "label": "玩家B遗物",
            "card": ("action_card_04.png", [974, 644, 1234, 1004], "卡面"),
            "icon": ("player_b_relic_icon.png", [1010, 670, 1202, 874], "图标_断剑"),
            "title_bbox": [1000, 874, 1220, 939],
            "clock": None,
            "timer_bbox": None,
            "arrow": None,
            "note": "第二份遗物，独立按钮",
            "color": COLOR_VIOLET,
        },
        {
            "id": "05",
            "group": "02_按钮_05_撤离",
            "label": "撤离",
            "card": ("action_card_05.png", [1238, 644, 1502, 1004], "卡面"),
            "icon": ("retreat_portal_icon.png", [1264, 662, 1478, 874], "图标_撤离传送门"),
            "title_bbox": [1300, 870, 1460, 922],
            "clock": ("timer_clock_02.png", [1323, 937, 1351, 965], "图标_读条时钟"),
            "timer_bbox": [1352, 924, 1470, 966],
            "arrow": None,
            "note": "本格有撤离点才出现；读条约 3.0s",
            "color": COLOR_GREEN,
        },
        {
            "id": "06",
            "group": "02_按钮_06_走邻格",
            "label": "走邻格",
            "card": ("action_card_06.png", [1504, 644, 1778, 1004], "卡面"),
            "icon": ("next_cell_door_icon.png", [1532, 662, 1746, 874], "图标_邻格门洞"),
            "title_bbox": [1540, 874, 1730, 939],
            "clock": None,
            "timer_bbox": None,
            "arrow": ("next_arrow_icon.png", [1708, 778, 1744, 826], "图标_方向箭头"),
            "note": "可走邻格才出现；无按钮不要灰置占位",
            "color": COLOR_BLUE,
        },
    ]

    for btn in buttons:
        prefix = f"02_{btn['id']}"
        card_file, card_bbox, card_name = btn["card"]
        arr, x, y = place_sprite(sprite_dir, card_file, card_bbox)
        add(f"{prefix}_{card_name}", card_name, arr, x, y, btn["group"], "card", btn["note"])

        icon_file, icon_bbox, icon_name = btn["icon"]
        arr, x, y = place_sprite(sprite_dir, icon_file, icon_bbox)
        add(f"{prefix}_{icon_name}", icon_name, arr, x, y, btn["group"], "icon")

        text = extract_text(orig, clean, btn["title_bbox"], pad=3, kind="gold")
        add(f"{prefix}_文字_{btn['label']}", f"文字_{btn['label']}", text[0], text[1], text[2], btn["group"], "text", f"可替换文案：{btn['label']}")

        if btn["clock"]:
            clock_file, clock_bbox, clock_name = btn["clock"]
            arr, x, y = place_sprite(sprite_dir, clock_file, clock_bbox)
            add(f"{prefix}_{clock_name}", clock_name, arr, x, y, btn["group"], "icon", "读条时钟")
        if btn["timer_bbox"]:
            text = extract_text(orig, clean, btn["timer_bbox"], pad=2, kind="cyan")
            timer_label = "1.2s" if btn["id"] == "01" else "3.0s"
            add(f"{prefix}_文字_{timer_label}", f"文字_{timer_label}", text[0], text[1], text[2], btn["group"], "text", f"读条秒数 {timer_label}")
        if btn["arrow"]:
            arrow_file, arrow_bbox, arrow_name = btn["arrow"]
            arr, x, y = place_sprite(sprite_dir, arrow_file, arrow_bbox)
            add(f"{prefix}_{arrow_name}", arrow_name, arr, x, y, btn["group"], "icon", "邻格方向")

    preview = np.zeros((CANVAS[1], CANVAS[0], 4), np.uint8)
    for rec in records:
        overlay(preview, packed[rec["id"]][0], rec["left"], rec["top"])
    err = np.abs(preview.astype(np.int16) - orig.astype(np.int16))
    index = {
        "module": "ui_action",
        "gdd": "§7.1 清怪后行动栏",
        "canvas": {"width": CANVAS[0], "height": CANVAS[1]},
        "source": "ui_action_1920x1080.png",
        "psd": "ui_action_1920x1080.psd",
        "preview": "ui_action_1920x1080_preview.png",
        "reconstruction_mae_rgb": float(err[:, :, :3].mean()),
        "layer_stack": "Photoshop 图层顶 = 前景。00_背景 在最底，行动按钮分组可独立开关。",
        "groups": [
            {"name": "00_背景", "purpose": "地牢场景，UI 已挖空并补全"},
            {"name": "01_战斗结束", "purpose": "左上角徽章 + 可替换文字"},
            {"name": "02_行动栏", "purpose": "并列按钮，有才出现；关闭某一组即模拟该按钮不存在"},
        ],
        "layers": records,
    }
    (OUT_DIR / "ui_action_layer_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    write_psd(records, packed, orig)
    print(f"layers {len(records)}  MAE {index['reconstruction_mae_rgb']:.3f}")


def write_psd(records: list[dict], packed: dict, orig: np.ndarray) -> None:
    def keys_in(group: str) -> list[str]:
        return [r["id"] for r in records if r["group"] == group]

    def layers_for(group: str, color: int = 0):
        # Front of the group first, matching the Photoshop layer list.
        out = []
        for rec in reversed(keys_in(group)):
            arr, x, y = packed[rec]
            item = next(r for r in records if r["id"] == rec)
            out.append(image_layer(item["name"], arr, item["left"], item["top"], color=color))
        return out

    buttons = [
        ("02_按钮_01_生命泉水", "按钮_01_生命泉水", COLOR_ORANGE),
        ("02_按钮_02_使用生命药剂", "按钮_02_使用生命药剂", COLOR_BLUE),
        ("02_按钮_03_玩家A遗物", "按钮_03_玩家A遗物", COLOR_VIOLET),
        ("02_按钮_04_玩家B遗物", "按钮_04_玩家B遗物", COLOR_VIOLET),
        ("02_按钮_05_撤离", "按钮_05_撤离", COLOR_GREEN),
        ("02_按钮_06_走邻格", "按钮_06_走邻格", COLOR_BLUE),
    ]

    action = group(
        "02_行动栏",
        [
            *[
                group(label, layers_for(g, color), color=color)
                for g, label, color in buttons
            ],
            group("标题_当前格行动", layers_for("02_标题_当前格行动", COLOR_YELLOW), color=COLOR_YELLOW),
            image_layer(
                "底板_行动面板",
                packed["02_底板_行动面板"][0],
                next(r for r in records if r["id"] == "02_底板_行动面板")["left"],
                next(r for r in records if r["id"] == "02_底板_行动面板")["top"],
                color=COLOR_BLUE,
            ),
        ],
        color=COLOR_BLUE,
    )
    hud = group("01_战斗结束", layers_for("01_战斗结束", COLOR_YELLOW), color=COLOR_YELLOW)
    bg = group("00_背景", layers_for("00_背景", COLOR_GRAY), color=COLOR_GRAY)
    reference = image_layer("_参考_原效果图", orig, 0, 0, visible=False, color=COLOR_GRAY)

    preview = np.zeros((CANVAS[1], CANVAS[0], 4), np.uint8)
    for rec in records:
        overlay(preview, packed[rec["id"]][0], rec["left"], rec["top"])
    preview[:, :, 3] = 255

    psd_path = OUT_DIR / "ui_action_1920x1080.psd"
    write_cc2018_psd(
        psd_path,
        CANVAS[0],
        CANVAS[1],
        [reference, action, hud, bg],
        preview[:, :, :3],
    )
    Image.fromarray(preview).save(OUT_DIR / "ui_action_1920x1080_preview.png")
    print(f"PSD  {psd_path}  ({psd_path.stat().st_size / 1e6:.1f} MB)")


def pack_from_index() -> None:
    index_path = OUT_DIR / "ui_action_layer_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    records = index["layers"]
    packed = {}
    for rec in records:
        arr = load_rgba(OUT_DIR / rec["file"])
        packed[rec["id"]] = (arr, rec["left"], rec["top"])
    orig = load_rgba(OUT_DIR / index["source"])
    write_psd(records, packed, orig)


if __name__ == "__main__":
    src = Path("/tmp/ui_action_keep")
    if (src / "ui_action_1920x1080.png").exists() and (src / "sprites").exists():
        main()
    else:
        pack_from_index()
