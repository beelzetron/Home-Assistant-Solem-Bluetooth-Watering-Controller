#!/usr/bin/env python3
"""
Discover how to poll Solem BL-IP status over BLE (no side effects if possible).

Run (from repo root or anywhere):
  python3 scripts/ble_status_poll_discovery.py
  SOLEM_MAC=C8:B9:61:D4:4D:C8 python3 scripts/ble_status_poll_discovery.py

Paste the full terminal output back for analysis.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import struct
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bleak import BleakClient

WRITE_CHAR_UUID = "108b0002-eab5-bc09-d0ea-0b8f467ce8ee"
NOTIFY_CHAR_UUID = "108b0003-eab5-bc09-d0ea-0b8f467ce8ee"

DEFAULT_MAC = "C8:B9:61:D4:4D:C8"
MAX_STATION_NUM = 6
LOG_PATH = "/tmp/ble_status_poll_discovery.json"


@dataclass
class ParsedNotification:
    raw_hex: str
    response_type: int | None
    sequence: int | None
    status_byte: int | None
    station_num: int | None
    time_14_16: int | None
    time_16_18: int | None
    time_13_15: int | None
    parsed_status: dict[str, Any] | None
    skip_reason: str | None = None


@dataclass
class PollResult:
    test_id: str
    description: str
    command_hex: str | None
    commit: bool
    wait_seconds: float
    notifications: list[ParsedNotification] = field(default_factory=list)
    best_status: dict[str, Any] | None = None
    error: str | None = None


def parse_status_packet(data: bytes) -> tuple[dict[str, Any] | None, str | None]:
    """Match recommended integration parsing (seq 0x02 only)."""
    if len(data) < 18:
        return None, "len<18"
    if data[2] != 0x02:
        return None, f"seq={data[2]} (not 0x02)"
    if data[3] == 0x10:
        return None, "status=0x10 intermediate"

    status_byte = data[3]
    is_on = bool(status_byte & 0x40)
    is_watering = bool(status_byte & 0x02)
    station_raw = data[9]
    station_num = station_raw if 1 <= station_raw <= MAX_STATION_NUM else None

    remaining_seconds = None
    if is_watering:
        t1416 = struct.unpack(">H", data[14:16])[0]
        t1618 = struct.unpack(">H", data[16:18])[0]
        best = max(t1416, t1618)
        if best == 16 and t1618 == 0:
            remaining_seconds = None
        elif best > 0:
            remaining_seconds = best

    return {
        "controller_state": "On" if is_on else "Off",
        "is_watering": is_watering,
        "station_num": station_num,
        "remaining_seconds": remaining_seconds,
        "status_byte": status_byte,
        "response_type": data[0],
    }, None


def parse_raw_notification(data: bytes) -> ParsedNotification:
    hex_data = data.hex()
    response_type = data[0] if len(data) > 0 else None
    sequence = data[2] if len(data) > 2 else None
    status_byte = data[3] if len(data) > 3 else None
    station_num = data[9] if len(data) > 9 else None
    time_13_15 = struct.unpack(">H", data[13:15])[0] if len(data) >= 15 else None
    time_14_16 = struct.unpack(">H", data[14:16])[0] if len(data) >= 16 else None
    time_16_18 = struct.unpack(">H", data[16:18])[0] if len(data) >= 18 else None
    parsed, skip_reason = parse_status_packet(data)
    return ParsedNotification(
        raw_hex=hex_data,
        response_type=response_type,
        sequence=sequence,
        status_byte=status_byte,
        station_num=station_num,
        time_13_15=time_13_15,
        time_14_16=time_14_16,
        time_16_18=time_16_18,
        parsed_status=parsed,
        skip_reason=skip_reason,
    )


def fmt_status(sb: int | None) -> str:
    if sb is None:
        return "N/A"
    on = "ON" if sb & 0x40 else "OFF"
    water = "WATERING" if sb & 0x02 else "IDLE"
    return f"0x{sb:02x} ({on}, {water})"


def print_notification(n: ParsedNotification, index: int) -> None:
    print(f"\n  --- notify #{index} ---")
    print(f"  hex:      {n.raw_hex}")
    print(f"  seq:      {n.sequence}  rt: 0x{n.response_type:02x}" if n.response_type is not None else f"  seq:      {n.sequence}")
    print(f"  status:   {fmt_status(n.status_byte)}")
    print(f"  station:  {n.station_num}")
    print(f"  time[13:15]={n.time_13_15}  [14:16]={n.time_14_16}  [16:18]={n.time_16_18}  (api.py uses [13:15] today)")
    if n.parsed_status:
        print(f"  PARSED:   {n.parsed_status}")
    else:
        print(f"  PARSED:   (skipped: {n.skip_reason})")


async def run_poll_test(
    client: BleakClient,
    test_id: str,
    description: str,
    command_hex: str | None,
    *,
    commit: bool = False,
    wait_seconds: float = 8.0,
    post_command_sleep: float = 0.5,
) -> PollResult:
    result = PollResult(
        test_id=test_id,
        description=description,
        command_hex=command_hex,
        commit=commit,
        wait_seconds=wait_seconds,
    )
    collected: list[ParsedNotification] = []
    best: dict[str, Any] | None = None

    def handler(_sender: int, data: bytearray) -> None:
        parsed = parse_raw_notification(bytes(data))
        collected.append(parsed)
        if parsed.parsed_status and nonlocal_best["value"] is None:
            nonlocal_best["value"] = parsed.parsed_status

    nonlocal_best: dict[str, Any] = {"value": None}

    print("\n" + "=" * 72)
    print(f"TEST {test_id}: {description}")
    print("=" * 72)
    if command_hex:
        print(f"  write:   {command_hex}")
    else:
        print("  write:   (none)")
    print(f"  commit:  {'3b00' if commit else '(no)'}")
    print(f"  listen:  {wait_seconds}s after trigger")

    try:
        await client.start_notify(NOTIFY_CHAR_UUID, handler)

        if command_hex:
            await client.write_gatt_char(WRITE_CHAR_UUID, bytes.fromhex(command_hex))
            await asyncio.sleep(post_command_sleep)

        if commit:
            await client.write_gatt_char(WRITE_CHAR_UUID, bytes.fromhex("3b00"))
            await asyncio.sleep(post_command_sleep)

        await asyncio.sleep(wait_seconds)

        await client.stop_notify(NOTIFY_CHAR_UUID)
    except Exception as ex:
        result.error = str(ex)
        print(f"  ERROR: {ex}")

    result.notifications = collected
    result.best_status = nonlocal_best["value"]

    seq2 = [n for n in collected if n.sequence == 2]
    print(f"\n  Summary: {len(collected)} notification(s), {len(seq2)} with seq=2")
    if result.best_status:
        print(f"  Best seq=0x02 status: {result.best_status}")
    else:
        print("  Best seq=0x02 status: NONE")

    for i, n in enumerate(collected, 1):
        print_notification(n, i)

    return result


async def main() -> int:
    parser = argparse.ArgumentParser(description="BLE status poll discovery for Solem BL-IP")
    parser.add_argument(
        "mac",
        nargs="?",
        default=os.environ.get("SOLEM_MAC", DEFAULT_MAC),
        help=f"Controller MAC (default: {DEFAULT_MAC} or SOLEM_MAC env)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Bleak connection timeout seconds (default: 60)",
    )
    args = parser.parse_args()
    mac = args.mac.upper()

    print("Solem BLE Status Poll Discovery")
    print(f"MAC:     {mac}")
    print(f"Write:   {WRITE_CHAR_UUID}")
    print(f"Notify:  {NOTIFY_CHAR_UUID}")
    print(f"Log:     {LOG_PATH}")
    print(f"Started: {datetime.now().isoformat()}")

    tests = [
        (
            "A",
            "Subscribe only (simulates current api.py get_status) — no write",
            None,
            False,
            8.0,
        ),
        (
            "B",
            "Commit only (3b00) — does commit trigger status?",
            None,
            True,
            8.0,
        ),
        (
            "C",
            "Command without commit — Turn ON write only",
            "3105a000000000",
            False,
            8.0,
        ),
        (
            "D",
            "Turn ON + commit (known good from prior tests)",
            "3105a000000000",
            True,
            8.0,
        ),
        (
            "E",
            "STOP + commit (read idle/stopped state)",
            "31051500ff0000",
            True,
            8.0,
        ),
    ]

    all_results: list[dict[str, Any]] = []

    try:
        async with BleakClient(mac, timeout=args.timeout) as client:
            print(f"\n[+] Connected: {client.is_connected}")

            for test_id, desc, cmd, commit, wait in tests:
                # Fresh notify subscription per test
                res = await run_poll_test(
                    client,
                    test_id,
                    desc,
                    cmd,
                    commit=commit,
                    wait_seconds=wait,
                )
                all_results.append(
                    {
                        "test_id": res.test_id,
                        "description": res.description,
                        "command_hex": res.command_hex,
                        "commit": res.commit,
                        "wait_seconds": res.wait_seconds,
                        "notification_count": len(res.notifications),
                        "seq2_count": sum(1 for n in res.notifications if n.sequence == 2),
                        "best_status": res.best_status,
                        "error": res.error,
                        "notifications": [
                            {
                                "hex": n.raw_hex,
                                "sequence": n.sequence,
                                "status_byte": n.status_byte,
                                "station_num": n.station_num,
                                "time_13_15": n.time_13_15,
                                "time_14_16": n.time_14_16,
                                "time_16_18": n.time_16_18,
                                "parsed_status": n.parsed_status,
                                "skip_reason": n.skip_reason,
                            }
                            for n in res.notifications
                        ],
                    }
                )
                await asyncio.sleep(2)

    except Exception as ex:
        print(f"\n[FATAL] Could not connect or run tests: {ex}")
        return 1

    print("\n" + "=" * 72)
    print("FINAL TABLE (paste this section)")
    print("=" * 72)
    print(f"{'ID':<4} {'Notifies':<9} {'Seq=2':<6} {'Got status?':<12} Best status")
    print("-" * 72)
    for r in all_results:
        got = "YES" if r["best_status"] else "NO"
        best = r["best_status"] or "-"
        print(
            f"{r['test_id']:<4} {r['notification_count']:<9} {r['seq2_count']:<6} "
            f"{got:<12} {best}"
        )

    print("\nInterpretation:")
    print("  A=YES -> passive notify works (unlikely from prior 5min test)")
    print("  B=YES -> commit-only is enough for get_status() poll")
    print("  D=YES -> need a harmless read command; Turn ON has side effects")
    print("  Compare time columns: [14:16] vs [16:18] vs api.py [13:15]")

    payload = {
        "mac": mac,
        "started": datetime.now().isoformat(),
        "results": all_results,
    }
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\n[+] JSON log: {LOG_PATH}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n[!] Interrupted")
        sys.exit(130)
