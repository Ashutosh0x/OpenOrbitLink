from __future__ import annotations

"""
Interactive OpenOrbitLink simulation.

This demo runs without RF hardware. It builds a band-aware packet, queues it in
DTN, estimates link/throughput costs, and shows the FOSSA/TinyGS frame that
would be handed to a station client.
"""

import tempfile
from pathlib import Path

from protocol.dtn import DTNEngine
from protocol.fossa import packet_payload_to_fossa_frames
from protocol.packet import OpenOrbitLinkProtocol, TransmitBand
from simulation.link_budget import LinkBudgetParams, TxPath, analyze_throughput, compute_link_budget


def choose_band() -> TransmitBand:
    print("\nBand:")
    print("  1. ISM LoRa satellite path (encryption allowed)")
    print("  2. Amateur APRS/packet path (plaintext only, license required)")
    choice = input("Select [1]: ").strip() or "1"
    return TransmitBand.AMATEUR if choice == "2" else TransmitBand.ISM


def run_once() -> None:
    message = input("Message [Hello from OpenOrbitLink]: ").strip() or "Hello from OpenOrbitLink"
    band = choose_band()
    encrypted = False
    if band == TransmitBand.ISM:
        encrypted = (input("Mark payload as encrypted? [y/N]: ").strip().lower() == "y")
    elif input("Try encrypted amateur packet? [y/N]: ").strip().lower() == "y":
        encrypted = True

    proto = OpenOrbitLinkProtocol("demo-device")
    try:
        packet = proto.create_text_message(message, band=band, encrypt=encrypted)
        raw = packet.serialize()
    except Exception as exc:
        print(f"\nBlocked: {exc}")
        return

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "demo_bundles.db")
        dtn = DTNEngine(proto, db_path=db_path)
        bundle_id = dtn.queue_message(packet, destination="demo-peer")
        print(f"\nQueued bundle: {bundle_id}")
        print(f"Packet bytes: {len(raw)}")
        print(f"Band: {packet.transmit_band.name}, encrypted flag: {packet.is_encrypted}")

        path = TxPath.HAM_SDR_UPLINK if band == TransmitBand.AMATEUR else TxPath.LORA_ISM_UPLINK
        budget = compute_link_budget(LinkBudgetParams(tx_path=path, elevation_deg=30.0))
        throughput = analyze_throughput(len(packet.payload), raw_bitrate_bps=700.0)
        print(f"TX path: {budget['tx_path']} ({'viable' if budget['is_viable'] else 'not viable'})")
        print(f"Reason: {budget['reason']}")
        print(f"Estimated 700 bps packet time: {throughput.tx_time_seconds:.2f}s")
        print(f"Effective payload rate: {throughput.effective_payload_bps:.1f} bps")

        if band == TransmitBand.ISM:
            frames = packet_payload_to_fossa_frames(packet.payload_type, packet.payload, encrypted=packet.is_encrypted)
            print(f"FOSSA frames: {len(frames)}")
            print(f"First frame base64: {frames[0].to_base64()}")


def main() -> None:
    print("OpenOrbitLink Offline Simulation")
    print("==============================")
    while True:
        run_once()
        again = input("\nRun another simulation? [y/N]: ").strip().lower()
        if again != "y":
            break


if __name__ == "__main__":
    main()
