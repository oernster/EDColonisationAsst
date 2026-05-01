"""Find which local process is listening on a TCP port (Windows).

Stdlib only. Useful to confirm which backend instance is serving
http://127.0.0.1:8000 when results don't match the workspace code.

Run from repo root:

  c:/Users/Oliver/Development/EDColonisationAsst/venv/Scripts/python backend/tools/find_port_owner.py 8000
"""

from __future__ import annotations

import re
import subprocess
import sys
from typing import Iterable


def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True, errors="replace", shell=False)


def _iter_listening_pids(port: int) -> Iterable[int]:
    out = _run(["netstat", "-ano", "-p", "tcp"])
    # Typical line:
    #   TCP    127.0.0.1:8000   0.0.0.0:0   LISTENING   12345
    pat = re.compile(rf"^\s*TCP\s+\S+:{port}\s+\S+\s+LISTENING\s+(\d+)\s*$")
    for line in out.splitlines():
        m = pat.match(line)
        if m:
            yield int(m.group(1))


def _tasklist(pid: int) -> str:
    try:
        return _run(["tasklist", "/FI", f"PID eq {pid}"])
    except Exception as exc:  # noqa: BLE001
        return f"Failed to query tasklist for PID {pid}: {exc!r}"


def main(argv: list[str]) -> int:
    port = int(argv[1]) if len(argv) > 1 else 8000
    pids = sorted(set(_iter_listening_pids(port)))
    if not pids:
        print(f"No LISTENING TCP sockets found on port {port}.")
        return 1

    print(f"Port {port} is LISTENING under PID(s): {pids}")
    for pid in pids:
        print("\n---")
        print(_tasklist(pid).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

