"""
scripts/snark_watch.py

Advances N checkpoints in sequence for a given steward and prints how
snark fields evolve each time. Useful for watching centroid convergence
and uncertainty radius decay over a simulated run.

Usage:
  python scripts/snark_watch.py --steward-id <id> --steward-key pm_... --checkpoints 10

If --steward-id and --steward-key are omitted, the script registers a
fresh steward with test pulses so you can run it against a clean DB.

Auth note: identity polls in the watch loop use the admin key, not the
steward pm_ key. The steward key rotates on every checkpoint advance,
so the registration key would 401 after the first advance. The watch
script is a node operator tool; admin key is correct here.
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from pulsermesh.client import PulserMeshClient, PulserMeshError


def fmt(v, digits=4):
    if v is None:
        return "None"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def print_row(cp_index, identity):
    fields = [
        fmt(cp_index),
        fmt(identity.get("pulse_count")),
        fmt(identity.get("null_centroid_za")),
        fmt(identity.get("mission_vector_za")),
        fmt(identity.get("mission_delta")),
    ]
    print("  ".join(f"{f:<14}" for f in fields))


def print_header():
    headers = ["checkpoint", "pulse_count", "null_centroid", "mission_vec", "mission_delta"]
    print("  ".join(f"{h:<14}" for h in headers))
    print("-" * 80)


def ensure_steward(client: PulserMeshClient, n_pulses: int = 8):
    """Register a fresh steward and seed it with n_pulses validated pulses."""
    resp = client.register_steward(
        "WatchSteward",
        domains=["water", "energy"],
        domain_weights={"water": 1.5, "energy": 1.0},
    )
    steward_id = resp["id"]
    steward_key = resp["api_key"]
    print(f"Registered steward {steward_id[:8]}... with mission domains: water, energy")

    pulse_ids = []
    domains = ["water", "energy"] * (n_pulses // 2) + ["water"] * (n_pulses % 2)
    for i, domain in enumerate(domains):
        p = client.submit_pulse(
            scarcity_domain=domain,
            description=f"seed pulse {i+1}",
            value_add=1.0,
            steward_key=steward_key,
        )
        pulse_ids.append(p["id"])

    validated = 0
    for pid in pulse_ids:
        try:
            client.validate_pulse(pid)
            validated += 1
        except PulserMeshError:
            pass
    print(f"Seeded {validated}/{n_pulses} validated pulses")
    return steward_id


def run(args):
    client = PulserMeshClient()

    if args.steward_id:
        steward_id = args.steward_id
        print(f"Watching existing steward {steward_id[:8]}...")
    else:
        print("No steward supplied — registering a fresh one...")
        steward_id = ensure_steward(client, n_pulses=args.seed_pulses)

    print()
    print_header()

    for i in range(args.checkpoints):
        cp = client.advance_checkpoint(ta_ref=float(i + 1))
        # Identity poll uses the admin key — the steward pm_ key rotates
        # on every checkpoint advance and would 401 after the first.
        identity = client._get(f"/stewards/{steward_id}/identity", client._admin_headers())
        print_row(cp.get("index"), identity)

    print()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Watch snark field evolution across checkpoints.")
    parser.add_argument("--steward-id",  default=None, help="Existing steward UUID")
    parser.add_argument("--checkpoints", type=int, default=10, help="Number of checkpoints to advance (default: 10)")
    parser.add_argument("--seed-pulses", type=int, default=8,  help="Pulses to seed if creating a fresh steward (default: 8)")
    args = parser.parse_args()
    try:
        run(args)
    except PulserMeshError as e:
        print(f"Server error: {e}")
        sys.exit(1)
