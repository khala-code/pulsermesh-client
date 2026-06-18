"""
scripts/snark_watch.py

Advances N checkpoints in sequence for a given steward and prints how
snark fields evolve each time. Useful for watching centroid convergence
and uncertainty radius decay over a simulated run.

Usage:
  # Fresh steward, 3 pulses per checkpoint, 15 checkpoints:
  python scripts/snark_watch.py --pulses-per-checkpoint 3 --checkpoints 15

  # Existing steward, no mid-run pulses:
  python scripts/snark_watch.py --steward-id <uuid> --checkpoints 10

If --steward-id is omitted a fresh steward is registered and seeded with
--seed-pulses validated pulses before the first advance.

Auth note: identity polls use the admin key. The steward pm_ key rotates
on every checkpoint advance; the watch script is a node operator tool.
"""
import sys
import os
import argparse
import itertools

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from pulsermesh.client import PulserMeshClient, PulserMeshError

DOMAINS = ["water", "energy"]


def fmt(v, digits=4):
    if v is None:
        return "None"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def print_row(cp_index, identity, uncertainty_radius=None):
    fields = [
        fmt(cp_index),
        fmt(identity.get("pulse_count")),
        fmt(identity.get("null_centroid_za")),
        fmt(identity.get("mission_vector_za")),
        fmt(identity.get("mission_delta")),
        fmt(uncertainty_radius),
    ]
    print("  ".join(f"{f:<14}" for f in fields))


def print_header():
    headers = ["checkpoint", "pulse_count", "null_centroid", "mission_vec", "mission_delta", "uncertainty_r"]
    print("  ".join(f"{h:<14}" for h in headers))
    print("-" * 96)


def submit_and_validate(client: PulserMeshClient, steward_id: str, steward_key: str, n: int, cp_index: int):
    """Submit and validate n pulses for steward, cycling through domains."""
    domain_cycle = itertools.cycle(DOMAINS)
    pulse_ids = []
    for i in range(n):
        try:
            p = client.submit_pulse(
                scarcity_domain=next(domain_cycle),
                description=f"watch pulse cp{cp_index}-{i+1}",
                value_add=1.0,
                steward_key=steward_key,
            )
            pulse_ids.append(p["id"])
        except PulserMeshError as e:
            print(f"  [warn] pulse submit failed: {e}")

    validated = 0
    for pid in pulse_ids:
        try:
            client.validate_pulse(pid)
            validated += 1
        except PulserMeshError:
            pass
    return validated


def ensure_steward(client: PulserMeshClient, n_pulses: int):
    """Register a fresh steward and seed it with n_pulses validated pulses."""
    resp = client.register_steward(
        "WatchSteward",
        domains=["water", "energy"],
        domain_weights={"water": 1.5, "energy": 1.0},
    )
    steward_id = resp["id"]
    steward_key = resp["api_key"]
    print(f"Registered steward {steward_id[:8]}... with mission domains: water, energy")

    if n_pulses > 0:
        validated = submit_and_validate(client, steward_id, steward_key, n_pulses, cp_index=0)
        print(f"Seeded {validated}/{n_pulses} validated pulses")

    return steward_id, steward_key


def compute_uncertainty_radius(identity: dict) -> float | None:
    """Client-side uncertainty radius estimate from pulse_count and ta."""
    import math
    n = identity.get("pulse_count") or 0
    ta = identity.get("ta") or 0.0
    if n < 1:
        return None
    # Mirrors asymptotic.uncertainty_band(n, ta) / sqrt(n)
    # lambda decay constant matches server default (0.1)
    base = (1.0 / math.sqrt(n)) * math.exp(-0.1 * ta)
    return base / math.sqrt(n)


def run(args):
    client = PulserMeshClient()

    if args.steward_id:
        steward_id = args.steward_id
        steward_key = None  # admin key used for identity polls; steward key not needed
        print(f"Watching existing steward {steward_id[:8]}...")
    else:
        print("No steward supplied — registering a fresh one...")
        steward_id, steward_key = ensure_steward(client, n_pulses=args.seed_pulses)

    print()
    print_header()

    for i in range(args.checkpoints):
        # Submit pulses before this advance if requested
        if args.pulses_per_checkpoint > 0 and steward_key:
            submit_and_validate(
                client, steward_id, steward_key,
                n=args.pulses_per_checkpoint,
                cp_index=i + 1,
            )

        cp = client.advance_checkpoint(ta_ref=float(i + 1))
        identity = client._get(f"/stewards/{steward_id}/identity", client._admin_headers())
        uncertainty_r = compute_uncertainty_radius(identity)
        print_row(cp.get("index"), identity, uncertainty_r)

    print()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Watch snark field evolution across checkpoints.")
    parser.add_argument("--steward-id", default=None, help="Existing steward UUID (skips registration)")
    parser.add_argument("--checkpoints", type=int, default=10, help="Checkpoints to advance (default: 10)")
    parser.add_argument("--seed-pulses", type=int, default=0, help="Pulses to seed before first advance (default: 0)")
    parser.add_argument("--pulses-per-checkpoint", type=int, default=3,
                        help="Pulses to submit+validate before each advance (default: 3)")
    args = parser.parse_args()
    try:
        run(args)
    except PulserMeshError as e:
        print(f"Server error: {e}")
        sys.exit(1)
