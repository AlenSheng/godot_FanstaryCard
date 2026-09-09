"""Encode the captured native viewport frames; no simulated or generated footage."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/.deps"))
import imageio_ffmpeg

folder = ROOT / "client/evidence/live"
report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
count = int(report["frames"])
assert count > 0
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-framerate", "2", "-i", str(folder / "frames/%04d.png"), "-frames:v", str(count), "-vf", "scale=960:540", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "26", str(folder / "gameplay.mp4")], check=True)
print(folder / "gameplay.mp4")
