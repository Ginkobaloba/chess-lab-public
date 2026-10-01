# Provenance: adapted from Ginkobaloba/draughts-lab train/hw.py at commit
# 0a5c5a0fe6cc3443565937a738509f5de9479b19 (Paradigm-owned, MIT). Changes: the
# default data root is D:/chess-lab-data, the dirty check covers chesslab/ and
# scripts/, and gpu_snapshot() was added.
"""Hardware and provenance facts from real system queries (for receipts)."""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys
from pathlib import Path

import psutil

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.environ.get("CHESS_LAB_DATA", "D:/chess-lab-data"))


def cpu_model() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    return platform.processor() or "unknown"


def gpu_models() -> list[str]:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def gpu_snapshot() -> str:
    try:
        return subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def hardware() -> dict[str, object]:
    return {
        "cpu_model": cpu_model(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cpus": psutil.cpu_count(logical=True),
        "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "gpus": gpu_models(),
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "python": platform.python_version(),
        "hostname_hash": hashlib.sha256(platform.node().encode()).hexdigest()[:12],
    }


def git_commit(repo: Path = REPO_ROOT) -> dict[str, object]:
    def run(*args: str) -> str:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout

    try:
        commit = run("rev-parse", "HEAD").strip()
        dirty = bool(
            run("status", "--porcelain", "--untracked-files=no").strip()
            or run("status", "--porcelain", "--", "chesslab", "scripts").strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return {"commit": "unknown", "dirty": None}
    return {"commit": commit, "dirty": dirty}


def set_low_priority() -> None:
    """BelowNormal on Windows, nice 10 elsewhere. Also pins BLAS to one thread."""
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(var, "1")
    proc = psutil.Process()
    try:
        if sys.platform == "win32":
            proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            proc.nice(10)
    except (psutil.Error, OSError):
        pass


def check_data_dir(path: Path) -> None:
    """Refuse a data or run directory inside C:/dev (mirrored/synced) or inside this repo."""
    resolved = Path(path).resolve()
    for root in (REPO_ROOT.resolve(), Path("C:/dev").resolve()):
        if resolved.is_relative_to(root):
            raise SystemExit(f"refusing data directory {resolved}: it is under {root}; use {DATA_ROOT}")


def sha256_file(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()
