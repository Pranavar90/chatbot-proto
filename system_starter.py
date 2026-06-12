#!/usr/bin/env python3
"""
system_starter.py — Planet Material Labs full-stack launcher
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Starts and monitors:
  ● Ollama          local LLM inference      :11434
  ● Qdrant          vector store (Docker)    :6333
  ● FastAPI         uvicorn backend          :8000
  ● Vite            React frontend           :5173

Features:
  - Live color-coded logs per service
  - API call highlighting (method · path · status)
  - Error / warning detection with visual callouts
  - Process crash detection and reporting
  - Health-check pings once each port is open
  - Clean Ctrl+C shutdown of all child processes
"""

import os
import re
import sys
import time
import signal
import shutil
import socket
import threading
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime

# ── ANSI ──────────────────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"

CF   = "\033[38;5;117m"   # frontend  — sky blue
CB   = "\033[38;5;208m"   # backend   — bridges orange
CO   = "\033[38;5;141m"   # ollama    — purple
CQ   = "\033[38;5;83m"    # qdrant    — green
CS   = "\033[38;5;245m"   # system    — gray
CE   = "\033[38;5;196m"   # error     — red
CW   = "\033[38;5;214m"   # warning   — amber
CA   = "\033[38;5;120m"   # api ok    — bright green
CAE  = "\033[38;5;203m"   # api err   — salmon
CHL  = "\033[38;5;51m"    # highlight — cyan

USE_COLOR = sys.stdout.isatty() or os.environ.get("FORCE_COLOR")

def c(code: str, text: str) -> str:
    return f"{code}{text}{RESET}" if USE_COLOR else text

TAGS = {
    "frontend": c(CF, "[ VITE   ]"),
    "backend":  c(CB, "[ API    ]"),
    "ollama":   c(CO, "[ OLLAMA ]"),
    "qdrant":   c(CQ, "[ QDRANT ]"),
    "system":   c(CS, "[ SYS    ]"),
}

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT        = Path(__file__).parent.resolve()
BACKEND_DIR = ROOT / "backend"
QDRANT_VOL  = ROOT / "backend" / "data" / "qdrant_storage"

# ── Global state ──────────────────────────────────────────────────────────────

_procs: dict[str, subprocess.Popen] = {}
_procs_lock   = threading.Lock()
_stop         = threading.Event()
_reported_up  = set()

# ── Utilities ─────────────────────────────────────────────────────────────────

def ts() -> str:
    return c(DIM, datetime.now().strftime("%H:%M:%S"))

def port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False

def cmd_exists(name: str) -> bool:
    return shutil.which(name) is not None

def _popen_kwargs() -> dict:
    """Extra kwargs for subprocess.Popen — isolate process on Windows."""
    kw: dict = {}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return kw

# ── Log printer ───────────────────────────────────────────────────────────────

# Match uvicorn/starlette HTTP log lines
_API_RE  = re.compile(r'"(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(\S+)\s+HTTP/[\d.]+"\s+(\d+)')
_ERR_KW  = ("error", "exception", "traceback", "critical", "fatal", "failed",
            "connectionrefusederror", "oserror", "runtimeerror")
_WARN_KW = ("warning", "warn:", "deprecated", "userwarning")

def _emit(service: str, line: str, is_stderr: bool = False) -> None:
    tag  = TAGS.get(service, TAGS["system"])
    text = line.rstrip()
    if not text:
        return

    # ── API call lines (backend only) ────────────────────────────────────────
    if service == "backend":
        m = _API_RE.search(text)
        if m:
            method, path, code = m.group(1), m.group(2), m.group(3)
            code_color = CA if code.startswith("2") else (CW if code.startswith(("3", "4")) else CAE)
            print(
                f"{ts()} {tag}  "
                f"{c(BOLD, method):<6} {c(CHL, path)} "
                f"{c(code_color, code)}",
                flush=True,
            )
            return

    # ── Error lines ──────────────────────────────────────────────────────────
    low = text.lower()
    if any(kw in low for kw in _ERR_KW):
        print(f"{ts()} {tag} {c(CE, text)}", flush=True)
        return

    # ── Warning lines ────────────────────────────────────────────────────────
    if any(kw in low for kw in _WARN_KW):
        print(f"{ts()} {tag} {c(CW, text)}", flush=True)
        return

    # ── Default ──────────────────────────────────────────────────────────────
    color = CE if is_stderr else ""
    print(f"{ts()} {tag} {c(color, text) if color else text}", flush=True)


def _stream(service: str, proc: subprocess.Popen) -> None:
    """Spawn two daemon threads that drain stdout/stderr of a process."""
    def drain(stream, is_stderr: bool):
        try:
            for raw in iter(stream.readline, b""):
                if _stop.is_set():
                    break
                _emit(service, raw.decode("utf-8", errors="replace"), is_stderr)
        except (OSError, ValueError):
            pass

    threading.Thread(target=drain, args=(proc.stdout, False), daemon=True).start()
    threading.Thread(target=drain, args=(proc.stderr, True),  daemon=True).start()


def _log_sys(text: str) -> None:
    print(f"{ts()} {TAGS['system']} {text}", flush=True)

# ── Service starters ──────────────────────────────────────────────────────────

def start_ollama() -> None:
    if not cmd_exists("ollama"):
        _log_sys(c(CW, "Ollama not found in PATH — skipping"))
        return
    if port_open(11434):
        _log_sys(c(CS, "Ollama already running on :11434"))
        _reported_up.add("ollama")
        return

    _log_sys(f"Starting {c(CO, 'Ollama serve')} ...")
    proc = subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **_popen_kwargs(),
    )
    with _procs_lock:
        _procs["ollama"] = proc
    _stream("ollama", proc)
    _log_sys(f"Ollama  PID {c(CO, str(proc.pid))}")


def start_qdrant() -> None:
    if not cmd_exists("docker"):
        _log_sys(c(CW, "Docker not found — skipping Qdrant container"))
        return
    if port_open(6333):
        _log_sys(c(CS, "Qdrant already running on :6333"))
        _reported_up.add("qdrant")
        return

    # Clean up stale container from previous run
    subprocess.run(
        ["docker", "rm", "-f", "qdrant_pml"],
        capture_output=True, timeout=8,
    )

    QDRANT_VOL.mkdir(parents=True, exist_ok=True)

    _log_sys(f"Starting {c(CQ, 'Qdrant')} via Docker ...")
    proc = subprocess.Popen(
        [
            "docker", "run", "--rm",
            "--name", "qdrant_pml",
            "-p", "6333:6333",
            "-p", "6334:6334",
            "-v", f"{QDRANT_VOL}:/qdrant/storage:z",
            "qdrant/qdrant",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **_popen_kwargs(),
    )
    with _procs_lock:
        _procs["qdrant"] = proc
    _stream("qdrant", proc)
    _log_sys(f"Qdrant  PID {c(CQ, str(proc.pid))}")


def start_backend() -> None:
    if port_open(8000):
        _log_sys(c(CS, "Backend already running on :8000"))
        _reported_up.add("backend")
        return

    python = sys.executable
    _log_sys(f"Starting {c(CB, 'FastAPI')} → {BACKEND_DIR} ...")
    proc = subprocess.Popen(
        [
            python, "-m", "uvicorn", "main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",
            "--log-level", "info",
        ],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **_popen_kwargs(),
    )
    with _procs_lock:
        _procs["backend"] = proc
    _stream("backend", proc)
    _log_sys(f"FastAPI PID {c(CB, str(proc.pid))}")


def start_frontend() -> None:
    if port_open(5173):
        _log_sys(c(CS, "Frontend already running on :5173"))
        _reported_up.add("frontend")
        return

    npm = shutil.which("npm") or "npm"
    _log_sys(f"Starting {c(CF, 'Vite')} → {ROOT} ...")
    proc = subprocess.Popen(
        [npm, "run", "dev"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **_popen_kwargs(),
    )
    with _procs_lock:
        _procs["frontend"] = proc
    _stream("frontend", proc)
    _log_sys(f"Vite    PID {c(CF, str(proc.pid))}")

# ── Health monitor ────────────────────────────────────────────────────────────

_HEALTH = {
    "ollama":   (11434, "http://127.0.0.1:11434"),
    "qdrant":   (6333,  "http://127.0.0.1:6333/healthz"),
    "backend":  (8000,  "http://127.0.0.1:8000/docs"),
    "frontend": (5173,  None),
}

_SVC_COLOR = {
    "frontend": CF, "backend": CB, "ollama": CO, "qdrant": CQ,
}

def _health_monitor() -> None:
    while not _stop.is_set():
        time.sleep(3)

        # ── Check for crashes ─────────────────────────────────────────────
        with _procs_lock:
            crashed = []
            for name, proc in _procs.items():
                if proc.poll() is not None:
                    crashed.append((name, proc.returncode))
            for name, _ in crashed:
                del _procs[name]

        for name, rc in crashed:
            if not _stop.is_set():
                _log_sys(
                    c(CE, f"{BOLD}[CRASH]{RESET}{CE} {name.upper()} "
                           f"exited with code {rc}")
                )

        # ── Health-check each service once ────────────────────────────────
        for svc, (port, url) in _HEALTH.items():
            if svc in _reported_up:
                continue
            if not port_open(port):
                continue
            if url:
                try:
                    urllib.request.urlopen(url, timeout=1.5)
                except Exception:
                    continue  # port open but HTTP not ready yet
            _reported_up.add(svc)
            col = _SVC_COLOR.get(svc, CS)
            _log_sys(c(col, f"{BOLD}✓ {svc.upper()} ready{RESET}  →  "
                            f"{url or f':{port}'}"))

        # ── All-up notification ───────────────────────────────────────────
        expected = {s for s in ("frontend", "backend", "ollama", "qdrant")
                    if s in _procs or s in _reported_up}
        if expected and expected == _reported_up & expected and "all" not in _reported_up:
            _reported_up.add("all")
            _log_sys(
                c(CA, f"{BOLD}ALL SERVICES UP{RESET}  "
                       f"─  frontend :5173  ·  api :8000  ·  "
                       f"ollama :11434  ·  qdrant :6333")
            )

# ── Shutdown ──────────────────────────────────────────────────────────────────

def _shutdown(sig=None, frame=None) -> None:
    _stop.set()
    print(f"\n{c(DIM, '─' * 60)}", flush=True)
    _log_sys(c(CS, "Stopping all services ..."))

    with _procs_lock:
        snap = dict(_procs)

    for name, proc in snap.items():
        _log_sys(f"Stopping {name} (PID {proc.pid})")
        try:
            if sys.platform == "win32":
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.terminate()
        except (ProcessLookupError, OSError):
            pass

    # Give processes a moment to exit cleanly
    time.sleep(1.5)

    # Force-kill anything still running
    for proc in snap.values():
        try:
            if proc.poll() is None:
                proc.kill()
        except (ProcessLookupError, OSError):
            pass

    # Stop named Docker container
    if "qdrant" in snap:
        try:
            subprocess.run(
                ["docker", "stop", "qdrant_pml"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass

    _log_sys(c(CS, "Done."))
    sys.exit(0)

# ── Header ────────────────────────────────────────────────────────────────────

def _print_header() -> None:
    W = 70
    bar   = c(DIM, "─" * W)
    title = c(CB + BOLD, "PLANET MATERIAL LABS  ·  SYSTEM STARTER")
    sub   = c(DIM, "PORTER STATION / KMC-01")
    print(f"\n{'':^{(W - len(title) + len(CB) + len(BOLD) + len(RESET))//2}}{title}", flush=True)
    print(f"  {sub}", flush=True)
    print(bar, flush=True)
    rows = [
        (CF, "VITE   ", "npm run dev",         "http://localhost:5173"),
        (CB, "API    ", "uvicorn  main:app",   "http://localhost:8000"),
        (CO, "OLLAMA ", "ollama serve",         "http://localhost:11434"),
        (CQ, "QDRANT ", "docker qdrant/qdrant", "http://localhost:6333"),
    ]
    for col, label, cmd, url in rows:
        print(
            f"  {c(col, f'● {label}')}  "
            f"{c(DIM, f'{cmd:<26}')}"
            f"{c(CHL, url)}",
            flush=True,
        )
    print(bar, flush=True)
    print(f"  {c(DIM, 'Ctrl+C to stop all services')}\n", flush=True)

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    # Enable ANSI escape codes on Windows terminal
    if sys.platform == "win32":
        os.system("")  # triggers VT100 mode in conhost/windows terminal

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    _print_header()

    # Staggered start: infra first, then backend, then frontend
    start_ollama();   time.sleep(0.4)
    start_qdrant();   time.sleep(0.4)
    start_backend();  time.sleep(0.4)
    start_frontend()

    # Health monitor in background
    threading.Thread(target=_health_monitor, daemon=True).start()

    _log_sys(c(CS, "All launchers started — streaming logs below ..."))
    print(c(DIM, "─" * 70), flush=True)

    try:
        while not _stop.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        _shutdown()


if __name__ == "__main__":
    main()
