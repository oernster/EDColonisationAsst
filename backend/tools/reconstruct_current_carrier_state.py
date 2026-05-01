"""Reconstruct /api/carriers/current/state from local journal files.

Run from repo root:

  c:/Users/Oliver/Development/EDColonisationAsst/venv/Scripts/python backend/tools/reconstruct_current_carrier_state.py

This script imports the backend domain logic and prints the reconstructed
carrier state exactly as the API would derive it (minus HTTP).
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    # Ensure we can import the backend package when executed from repo root.
    backend_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend_dir))

    from src.services.journal_parser import JournalParser
    from src.services.carrier_service import (
        build_current_carrier_response,
        build_current_carrier_state_response,
    )

    journal_dir = Path(r"C:\Users\Oliver\Saved Games\Frontier Developments\Elite Dangerous")
    files = sorted(journal_dir.glob("Journal.*.log"), key=lambda p: p.stat().st_mtime)
    if not files:
        print(f"No Journal.*.log files found under: {journal_dir}")
        return 2

    max_files = 25
    files_to_parse = files[-max_files:]
    print(f"Parsing {len(files_to_parse)}/{len(files)} recent journal files...")

    parser = JournalParser()
    events = []
    for fp in files_to_parse:
        events.extend(parser.parse_file(fp))

    print(f"Relevant parsed events: {len(events)}")

    current = build_current_carrier_response(events)
    print("\n--- /carriers/current ---")
    print(f"docked_at_carrier={current.docked_at_carrier}")
    if current.carrier:
        print(
            f"carrier name={current.carrier.name} callsign={current.carrier.callsign} market_id={current.carrier.market_id} carrier_id={current.carrier.carrier_id}"
        )

    state_resp = build_current_carrier_state_response(events)
    print("\n--- /carriers/current/state ---")
    if state_resp is None or state_resp.carrier is None:
        print("No carrier state resolved")
        return 0

    st = state_resp.carrier
    print(
        f"identity name={st.identity.name} callsign={st.identity.callsign} market_id={st.identity.market_id} carrier_id={st.identity.carrier_id}"
    )
    print(f"snapshot_time={st.snapshot_time.isoformat()}")
    print(f"trade_orders_scope={getattr(st, 'trade_orders_scope', None)}")
    print(f"buy_orders={len(st.buy_orders)} sell_orders={len(st.sell_orders)} cargo_rows={len(st.cargo)}")

    if st.sell_orders:
        print("\nSELL orders (first 20):")
        for o in st.sell_orders[:20]:
            print(
                f"- {o.commodity_name:24} price={o.price} orig={o.original_amount} remaining={o.remaining_amount} stock={o.stock}"
            )

    if st.buy_orders:
        print("\nBUY orders (first 20):")
        for o in st.buy_orders[:20]:
            print(
                f"- {o.commodity_name:24} price={o.price} orig={o.original_amount} remaining={o.remaining_amount} stock={o.stock}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

