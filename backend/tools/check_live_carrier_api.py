"""Check what the *running* backend returns for carrier endpoints.

This uses only the Python standard library (no requests dependency).

Run from repo root:

  c:/Users/Oliver/Development/EDColonisationAsst/venv/Scripts/python backend/tools/check_live_carrier_api.py
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request


def _get_json(url: str, *, timeout_s: float = 2.0) -> object:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


def main() -> int:
    base = "http://127.0.0.1:8000"
    endpoints = [
        f"{base}/api/health",
        f"{base}/api/carriers/current",
        f"{base}/api/carriers/current/state",
    ]

    for url in endpoints:
        print(f"\n=== {url} ===")
        try:
            data = _get_json(url)
        except urllib.error.HTTPError as e:
            print(f"HTTPError: {e.code} {e.reason}")
            try:
                print(e.read().decode("utf-8", errors="replace")[:2000])
            except Exception:
                pass
            continue
        except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
            print(f"Connection error: {e!r}")
            continue

        # Pretty-print a small, stable subset so diffs are obvious.
        if url.endswith("/api/carriers/current/state"):
            carrier = (data or {}).get("carrier") if isinstance(data, dict) else None
            if not isinstance(carrier, dict):
                print(json.dumps(data, indent=2)[:2000])
                continue

            ident = carrier.get("identity") or {}
            sell = carrier.get("sell_orders") or []
            buy = carrier.get("buy_orders") or []
            cargo = carrier.get("cargo") or []

            print(
                json.dumps(
                    {
                        "identity": {
                            "name": ident.get("name"),
                            "callsign": ident.get("callsign"),
                            "market_id": ident.get("market_id"),
                            "carrier_id": ident.get("carrier_id"),
                        },
                        "snapshot_time": carrier.get("snapshot_time"),
                        "trade_orders_scope": carrier.get("trade_orders_scope"),
                        "counts": {
                            "buy_orders": len(buy) if isinstance(buy, list) else None,
                            "sell_orders": len(sell) if isinstance(sell, list) else None,
                            "cargo_rows": len(cargo) if isinstance(cargo, list) else None,
                        },
                        "sell_orders_preview": sell[:5] if isinstance(sell, list) else None,
                        "buy_orders_preview": buy[:5] if isinstance(buy, list) else None,
                    },
                    indent=2,
                )
            )
        else:
            print(json.dumps(data, indent=2)[:2000])

    # Also compute what *this workspace code* reconstructs from the same journal
    # directory, so we can detect "running server is on old code" situations.
    try:
        # Ensure we can import backend package when executed from repo root.
        import sys
        from pathlib import Path

        backend_dir = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(backend_dir))

        from src.services.journal_parser import JournalParser
        from src.services.carrier_service import build_current_carrier_state_response

        journal_dir = Path(r"C:\Users\Oliver\Saved Games\Frontier Developments\Elite Dangerous")
        files = sorted(journal_dir.glob("Journal.*.log"), key=lambda p: p.stat().st_mtime)
        files_to_parse = files[-25:]

        parser = JournalParser()
        events = []
        for fp in files_to_parse:
            events.extend(parser.parse_file(fp))

        st_resp = build_current_carrier_state_response(events)
        carrier = st_resp.carrier if st_resp and st_resp.carrier else None

        print("\n=== Local reconstruction (workspace code) ===")
        if carrier is None:
            print("No carrier state resolved")
        else:
            print(
                json.dumps(
                    {
                        "snapshot_time": carrier.snapshot_time.isoformat(),
                        "trade_orders_scope": getattr(carrier, "trade_orders_scope", None),
                        "counts": {
                            "buy_orders": len(carrier.buy_orders),
                            "sell_orders": len(carrier.sell_orders),
                            "cargo_rows": len(carrier.cargo),
                        },
                    },
                    indent=2,
                )
            )
    except Exception as e:  # noqa: BLE001
        print("\n=== Local reconstruction (workspace code) ===")
        print(f"ERROR: {e!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

