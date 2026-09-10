#!/usr/bin/env python3
"""Render the original FantasyCard SFX library from deterministic synthesis."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE = 48000
SEED = 20260910


class Sound:
    def __init__(self, key: str, duration: float):
        self.key = key
        self.samples = np.zeros(round(duration * SAMPLE_RATE), dtype=np.float64)
        digest = hashlib.sha256(f"{SEED}:{key}".encode("ascii")).digest()
        self.rng = np.random.default_rng(int.from_bytes(digest[:8], "little"))

    def add(self, samples: np.ndarray, start: float = 0, gain: float = 1) -> None:
        first = round(start * SAMPLE_RATE)
        count = min(len(samples), len(self.samples) - first)
        if count > 0:
            self.samples[first : first + count] += samples[:count] * gain

    def noise(
        self, duration: float, low: float, high: float, decay: float,
        attack: float = 0.003,
    ) -> np.ndarray:
        time = np.arange(round(duration * SAMPLE_RATE)) / SAMPLE_RATE
        sos = signal.butter(2, [low, high], btype="bandpass", fs=SAMPLE_RATE, output="sos")
        samples = signal.sosfilt(sos, self.rng.normal(size=len(time)))
        samples /= max(np.std(samples), 1e-9)
        envelope = (1 - np.exp(-time / attack)) * np.exp(-time / decay)
        return samples * envelope

    def modes(
        self, duration: float, fundamental: float, ratios: list[float], decay: float,
        attack: float = 0.0015,
    ) -> np.ndarray:
        # Inharmonic modes and unequal damping resemble struck material, not a beep.
        time = np.arange(round(duration * SAMPLE_RATE)) / SAMPLE_RATE
        samples = np.zeros_like(time)
        for index, ratio in enumerate(ratios):
            frequency = fundamental * ratio
            if frequency >= SAMPLE_RATE * 0.46:
                continue
            damping = decay / (1 + index * 0.29)
            phase = self.rng.uniform(-0.13, 0.13)
            amplitude = 1 / (1 + index * 0.7)
            samples += amplitude * np.sin(2 * np.pi * frequency * time + phase) * np.exp(-time / damping)
        return samples * (1 - np.exp(-time / attack))

    def paper(self, start: float, duration: float, gain: float = 1, rough: bool = False) -> None:
        time = np.arange(round(duration * SAMPLE_RATE)) / SAMPLE_RATE
        friction = self.noise(duration, 900 if rough else 1700, 7500, duration * 0.42)
        motion = np.sin(np.pi * np.minimum(time / duration, 1)) ** 0.6
        grain = 0.7 + 0.3 * np.sin(2 * np.pi * (71 * time + 380 * time * time)) ** 2
        self.add(friction * motion * grain, start, gain)

    def stone(self, start: float, gain: float = 1, frequency: float = 145) -> None:
        self.add(self.noise(0.23, 100, 1900, 0.028), start, gain * 0.38)
        self.add(self.modes(0.25, frequency, [1, 1.43, 2.12, 3.39, 5.01], 0.038), start, gain)

    def brass(self, start: float, gain: float = 1, frequency: float = 680, decay: float = 0.12) -> None:
        self.add(self.noise(0.08, 1500, 7300, 0.007), start, gain * 0.16)
        self.add(self.modes(decay * 5.5, frequency, [1, 1.51, 2.09, 2.82, 3.79], decay), start, gain)

    def droplet(self, start: float, gain: float = 1, frequency: float = 950) -> None:
        time = np.arange(round(0.14 * SAMPLE_RATE)) / SAMPLE_RATE
        phase = 2 * np.pi * frequency * (time + 0.6 * 0.025 * (1 - np.exp(-time / 0.025)))
        plink = np.sin(phase) * np.exp(-time / 0.021) * (1 - np.exp(-time / 0.001))
        self.add(plink, start, gain)
        self.add(self.noise(0.1, 550, 4500, 0.016), start, gain * 0.12)

    def air(self, start: float, duration: float, gain: float = 1, dark: bool = False) -> None:
        time = np.arange(round(duration * SAMPLE_RATE)) / SAMPLE_RATE
        wind = self.noise(duration, 130 if dark else 500, 2500 if dark else 5800, duration * 1.2, 0.012)
        envelope = np.sin(np.pi * time / duration) ** 1.8
        self.add(wind * envelope, start, gain)

    def finish(self, peak_dbfs: float) -> np.ndarray:
        samples = self.samples - np.mean(self.samples)
        # Short cosine fades eliminate splice clicks; soft saturation only rounds transients.
        count = min(round(SAMPLE_RATE * 0.004), len(samples) // 4)
        fade = np.sin(np.linspace(0, np.pi / 2, count)) ** 2
        samples[:count] *= fade
        samples[-count:] *= fade[::-1]
        samples = np.tanh(samples * 0.7)
        samples *= 10 ** (peak_dbfs / 20) / max(np.max(np.abs(samples)), 1e-9)
        return np.round(samples * 32767).astype(np.int16)


def build_library() -> list[tuple[Sound, float, str]]:
    result: list[tuple[Sound, float, str]] = []

    def record(sound: Sound, peak: float, description: str) -> None:
        result.append((sound, peak, description))

    s = Sound("ui_click", 0.14)
    s.stone(0, 0.6, 330)
    s.add(s.noise(0.07, 1800, 5600, 0.007), gain=0.13)
    record(s, -17, "Soft fingertip on a small brass-inlaid stone control.")

    s = Sound("card_select", 0.15)
    s.paper(0, 0.10, 0.8)
    s.add(s.modes(0.12, 480, [1, 2.23, 3.9], 0.013), 0.018, 0.12)
    record(s, -17, "A dry parchment edge lifted from the hand; quiet for repeated selection.")

    s = Sound("card_draw", 0.25)
    s.paper(0, 0.16, 0.7)
    s.paper(0.055, 0.16, 0.45, rough=True)
    s.add(s.noise(0.1, 500, 3300, 0.009), 0.14, 0.18)
    record(s, -14, "Two overlapping parchment slides and a restrained edge flick.")

    s = Sound("card_play", 0.30)
    s.paper(0, 0.12, 0.65, rough=True)
    s.stone(0.063, 0.32, 210)
    s.air(0.015, 0.18, 0.10)
    record(s, -12, "Parchment cast onto a stone table, with a soft felt-backed landing.")

    s = Sound("hit_direct", 0.27)
    s.stone(0, 0.85, 112)
    s.add(s.noise(0.18, 350, 3600, 0.032), gain=0.45)
    record(s, -10, "A compact leather-and-stone impact with no elemental resonance.")

    s = Sound("hit_fire", 0.39)
    s.add(s.noise(0.33, 160, 5000, 0.10), gain=0.46)
    s.stone(0, 0.20, 96)
    for start, gain in [(0.026, 0.30), (0.087, 0.19), (0.152, 0.10), (0.225, 0.055)]:
        s.add(s.noise(0.055, 1800, 7800, 0.004), start, gain)
    record(s, -10, "A brief furnace flare, warm impact, and fading ember crackle.")

    s = Sound("hit_water", 0.43)
    s.add(s.noise(0.35, 250, 2600, 0.075), gain=0.38)
    s.air(0.005, 0.2, 0.10)
    for start, gain, frequency in [(0.015, 0.42, 430), (0.053, 0.30, 720), (0.123, 0.20, 970), (0.219, 0.10, 630)]:
        s.droplet(start, gain, frequency)
    record(s, -11, "A cool, hollow water strike followed by four diminishing droplets.")

    s = Sound("hit_wood", 0.32)
    s.add(s.modes(0.24, 205, [1, 2.74, 4.36, 6.13], 0.027), gain=0.8)
    for start, gain in [(0, 0.35), (0.022, 0.23), (0.059, 0.12)]:
        s.add(s.noise(0.10, 750, 4300, 0.010), start, gain)
    s.paper(0.055, 0.19, 0.13, rough=True)
    record(s, -11, "A dry root-and-bark snap with a low wooden body and rustling leaves.")

    s = Sound("hit_metal", 0.48)
    s.brass(0, 0.75, 455, 0.077)
    s.stone(0, 0.25, 160)
    s.add(s.noise(0.12, 1300, 6100, 0.014), gain=0.2)
    record(s, -11, "A worn bronze edge struck against armor; a short, dark inharmonic ring.")

    s = Sound("hit_earth", 0.42)
    s.stone(0, 0.7, 78)
    s.stone(0.043, 0.25, 124)
    s.add(s.noise(0.36, 70, 950, 0.085), gain=0.24)
    for start in [0.072, 0.119, 0.185]:
        s.add(s.noise(0.08, 900, 3900, 0.012), start, 0.10)
    record(s, -10, "A sandstone thump with small gravel settling behind the impact.")

    s = Sound("heal", 0.64)
    s.air(0, 0.48, 0.11)
    s.droplet(0.020, 0.15, 520)
    s.add(s.modes(0.54, 510, [1, 2.01, 3.98], 0.12, 0.03), 0.02, 0.27)
    s.add(s.modes(0.42, 765, [1, 2.03, 4.11], 0.10, 0.025), 0.14, 0.16)
    record(s, -15, "A breath of cool water and two gentle resonant tones, suggesting recovery.")

    s = Sound("shield", 0.51)
    s.stone(0, 0.31, 173)
    s.brass(0.015, 0.20, 310, 0.10)
    s.air(0.01, 0.33, 0.12, dark=True)
    record(s, -13, "A heavy protective rim seats into place, followed by a muted bronze hum.")

    s = Sound("reward", 0.70)
    s.paper(0, 0.15, 0.10)
    for start, frequency, gain in [(0.01, 740, 0.45), (0.094, 1110, 0.24), (0.205, 1480, 0.17)]:
        s.brass(start, gain, frequency, 0.09)
    record(s, -13, "Three small treasure chimes, like warm brass tokens settling in a dish.")

    s = Sound("purchase", 0.39)
    s.brass(0, 0.35, 930, 0.048)
    s.brass(0.067, 0.25, 1270, 0.045)
    s.paper(0.025, 0.15, 0.11, rough=True)
    s.stone(0.104, 0.13, 270)
    record(s, -14, "Two coins counted over parchment with a soft counter tap.")

    s = Sound("upgrade", 0.93)
    s.air(0.01, 0.42, 0.14, dark=True)
    s.stone(0.09, 0.23, 156)
    for start, frequency, gain in [(0.09, 430, 0.38), (0.24, 645, 0.23), (0.38, 860, 0.22)]:
        s.brass(start, gain, frequency, 0.11)
    record(s, -12, "A restrained forge strike blossoms into a rising bronze resonance.")

    s = Sound("equip", 0.33)
    s.add(s.noise(0.10, 350, 2900, 0.020), gain=0.21)
    s.brass(0.033, 0.25, 575, 0.046)
    s.stone(0.071, 0.31, 255)
    record(s, -13, "A leather strap tightens and a weathered armor clasp closes.")

    s = Sound("potion", 0.49)
    s.add(s.modes(0.10, 335, [1, 2.31, 4.71], 0.014), gain=0.18)
    s.add(s.noise(0.10, 900, 5700, 0.012), gain=0.07)
    for start, frequency, gain in [(0.083, 360, 0.26), (0.163, 290, 0.23), (0.246, 465, 0.15)]:
        s.droplet(start, gain, frequency)
    record(s, -14, "A small cork releases, followed by a short, warm glass-bottle gurgle.")

    s = Sound("move", 0.26)
    s.add(s.noise(0.21, 180, 2500, 0.036), gain=0.31)
    s.stone(0.012, 0.35, 122)
    s.paper(0.05, 0.13, 0.085, rough=True)
    record(s, -16, "One soft bootstep across dusty stone, kept quiet for map movement.")

    s = Sound("extract_start", 0.82)
    s.air(0, 0.65, 0.18, dark=True)
    s.stone(0.017, 0.24, 132)
    s.add(s.modes(0.75, 220, [1, 1.502, 2.03, 3.08], 0.21, 0.075), 0.025, 0.30)
    s.brass(0.14, 0.12, 660, 0.115)
    record(s, -15, "An ancient stone gate wakes with a low airy resonance; a single cue, not a loop.")

    s = Sound("extract_success", 1.02)
    s.air(0, 0.60, 0.13)
    s.brass(0.005, 0.34, 440, 0.16)
    s.brass(0.115, 0.25, 660, 0.14)
    s.brass(0.26, 0.20, 880, 0.13)
    record(s, -12, "The gate opens into a warm three-note bronze release with a soft air tail.")

    s = Sound("death", 0.89)
    s.stone(0, 0.31, 70)
    s.add(s.noise(0.73, 75, 950, 0.17), gain=0.18)
    s.add(s.modes(0.79, 110, [1, 1.41, 2.08], 0.18, 0.03), 0.025, 0.23)
    s.air(0.055, 0.63, 0.055, dark=True)
    record(s, -14, "A low fallen-stone resonance fading into dust; solemn and restrained.")

    s = Sound("error", 0.26)
    s.stone(0, 0.38, 215)
    s.stone(0.092, 0.25, 170)
    record(s, -16, "Two quiet, descending wooden-stone knocks indicate an unavailable action.")
    return result


def inspect_pcm(pcm: np.ndarray) -> dict:
    samples = pcm.astype(np.float64) / 32768
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(samples**2)))
    active = np.flatnonzero(np.abs(samples) > 10 ** (-55 / 20))
    return {
        "duration_seconds": round(len(pcm) / SAMPLE_RATE, 4),
        "peak_dbfs": round(20 * math.log10(max(peak, 1e-12)), 3),
        "rms_dbfs": round(20 * math.log10(max(rms, 1e-12)), 3),
        "clipped_samples": int(np.count_nonzero((pcm == 32767) | (pcm == -32768))),
        "active_duration_seconds": round((active[-1] - active[0] + 1) / SAMPLE_RATE, 4) if len(active) else 0,
        "leading_silence_seconds": round(active[0] / SAMPLE_RATE, 4) if len(active) else len(pcm) / SAMPLE_RATE,
        "tail_level_dbfs": round(20 * math.log10(max(float(np.max(np.abs(samples[-240:]))), 1e-12)), 3),
        "dc_offset": round(float(np.mean(samples)), 8),
    }


def render(output: Path, evidence: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    manifest = {
        "format_version": 1,
        "library": "FantasyCard - Parchment, Stone and Brass",
        "sample_rate_hz": SAMPLE_RATE,
        "channels": 1,
        "encoding": "PCM_S16LE",
        "seed": SEED,
        "license": "CC0-1.0",
        "generator": "tools/generate_game_audio.py",
        "sounds": {},
    }
    preview = [np.zeros(round(0.35 * SAMPLE_RATE), dtype=np.int16)]
    position = 0.35
    preview_index = []
    checks = []
    for sound, target_peak, description in build_library():
        pcm = sound.finish(target_peak)
        path = output / f"{sound.key}.wav"
        wavfile.write(path, SAMPLE_RATE, pcm)
        actual_rate, actual_pcm = wavfile.read(path)
        stats = inspect_pcm(actual_pcm)
        passed = (
            actual_rate == SAMPLE_RATE and actual_pcm.dtype == np.int16 and actual_pcm.ndim == 1
            and stats["clipped_samples"] == 0 and stats["active_duration_seconds"] > 0.025
            and stats["leading_silence_seconds"] < 0.09 and stats["tail_level_dbfs"] < -42
            and stats["rms_dbfs"] > -45 and abs(stats["dc_offset"]) < 0.001
            and actual_pcm[0] == 0 and actual_pcm[-1] == 0
            and abs(stats["peak_dbfs"] - target_peak) < 0.01
        )
        checks.append({"key": sound.key, "passed": passed, **stats})
        manifest["sounds"][sound.key] = {
            "path": f"res://assets/audio/{sound.key}.wav", **stats,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "gain_db": 0.0, "description": description,
        }
        preview_index.append({"key": sound.key, "start_seconds": round(position, 3), "duration_seconds": stats["duration_seconds"], "description": description})
        preview.extend([pcm, np.zeros(round(0.45 * SAMPLE_RATE), dtype=np.int16)])
        position += len(pcm) / SAMPLE_RATE + 0.45
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    wavfile.write(evidence / "sound_preview.wav", SAMPLE_RATE, np.concatenate(preview))
    (evidence / "sound_preview_index.json").write_text(json.dumps(preview_index, indent=2) + "\n", encoding="utf-8")
    report = {"passed": all(item["passed"] for item in checks), "sound_count": len(checks), "checks": checks}
    (evidence / "sound_validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "sound_count": len(checks), "preview_duration_seconds": round(position, 3), "output": str(output)}, indent=2))
    if not report["passed"]:
        failed = [item["key"] for item in checks if not item["passed"]]
        raise SystemExit(f"Audio validation failed: {failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "client/assets/audio")
    parser.add_argument("--evidence", type=Path, default=ROOT / "artifacts/audio-font-validation")
    options = parser.parse_args()
    render(options.output, options.evidence)
