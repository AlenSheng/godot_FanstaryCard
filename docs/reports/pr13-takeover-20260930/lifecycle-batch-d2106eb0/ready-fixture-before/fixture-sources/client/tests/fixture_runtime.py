"""Keep each Godot fixture's settings and user data inside its evidence directory."""
import os
from pathlib import Path


def isolated_environment(work: Path, **overrides):
    env = dict(os.environ, **overrides)
    directories = {
        "XDG_DATA_HOME": work / "runtime" / "data",
        "XDG_CONFIG_HOME": work / "runtime" / "config",
        "XDG_CACHE_HOME": work / "runtime" / "cache",
    }
    if os.name == "nt":
        directories.update({"APPDATA": work / "runtime" / "roaming",
                            "LOCALAPPDATA": work / "runtime" / "local"})
    for key, directory in directories.items():
        directory.mkdir(parents=True, exist_ok=True)
        env[key] = str(directory)
    return env
