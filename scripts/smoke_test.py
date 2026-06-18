"""
scripts/smoke_test.py

Full lifecycle integration test:
  1. Register two stewards (Alice with domains, Bob without)
  2. Assert baseline snark fields are all None
  3. Submit 5 pulses per steward across two domains
  4. Validate all pulses (admin)
  5. Advance one checkpoint
  6. Assert snark fields are populated correctly
  7. Advance a second checkpoint to test stability

Usage:
  Create a .env file in the repo root (see README), then:
  python scripts/smoke_test.py
"""
import sys
import os

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env if present — silently skipped if python-dotenv is not installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from pulsermesh.client import PulserMeshClient, PulserMeshError

try:
    from rich.console import Console
    from rich.table import Table
    console = Console()
except ImportError:
    # Graceful fallback if rich is not installed
    class Console:
        def print(self, *args, **kwargs):
            print(*args)
        def rule(self, *args, **kwargs):
            print("-" * 60)
    class Table:
        pass
    console = Console()


PULSE_DOMAINS = ["water", "energy", "food", "water", "energy"]  # 5 pulses, 2 domains
PULSE_VALUE = 1.0


def step(n: int, total: int, label: str) -> None:
    console.rule(f"[bold cyan][{n}/{total}] {label}[/bold cyan]")


def assert_field(label: str, value, expected, check_fn=None):
    if check_fn:
        ok = check_fn(value)
    else:
        ok = value == expected
    status = "[green]✓[/green]" if ok else "[red]✗[/red]"
    console.print(f"  {status} {label}: {value!r}  (expected {expected!r})")
    if not ok:
        raise AssertionError(f"FAIL: {label} — got {value!r}, expected {expected!r}")


def run():
    client = PulserMeshClient()
    TOTAL = 8

    # ── health check ──────────────────────────────────────────────────────────
    step(1, TOTAL, "Health check")
    h = client.health()
    console.print(f"  status: {h}")

    # ── register stewards ─────────────────────────────────────────────────────
    step(2, TOTAL, "Registering stewards")

    alice_resp = client.register_steward(
        "Alice",
        domains=["water", "energy"],
        domain_weights={"water": 2.0, "energy": 1.0},
    )
    alice_id = alice_resp["id"]
    alice_key = alice_resp["api_key"]
    console.print(f"  Alice  id={alice_id[:8]}...  api_key={alice_key[:10]}...")
    console.print(f"         mission_vector_za={alice_resp.get('mission_vector_za')}")

    # Second client for Bob to keep keys separate
    bob_client = PulserMeshClient()
    bob_resp = bob_client.register_steward("Bob")
    bob_id = bob_resp["id"]
    bob_key = bob_resp["api_key"]
    console.print(f"  Bob    id={bob_id[:8]}...  api_key={bob_key[:10]}...")

    # ── baseline snark fields ─────────────────────────────────────────────────
    step(3, TOTAL, "Baseline snark fields (expect nulls except mission_vector_za for Alice)")

    alice_id_resp = client.get_identity(alice_id, alice_key)
    bob_id_resp = bob_client.get_identity(bob_id, bob_key)

    console.print("  Alice:")
    assert_field("    null_centroid_za", alice_id_resp.get("null_centroid_za"), None)
    assert_field("    mission_delta",    alice_id_resp.get("mission_delta"),    None)
    assert_field("    pulse_count",      alice_id_resp.get("pulse_count"),      0)
    assert_field(
        "    mission_vector_za",
        alice_id_resp.get("mission_vector_za"),
        "float in [0, 2π)",
        check_fn=lambda v: v is not None and 0.0 <= v < 6.284,
    )

    console.print("  Bob:")
    assert_field("    null_centroid_za",  bob_id_resp.get("null_centroid_za"),  None)
    assert_field("    mission_vector_za", bob_id_resp.get("mission_vector_za"), None)
    assert_field("    pulse_count",       bob_id_resp.get("pulse_count"),       0)

    # ── submit pulses ─────────────────────────────────────────────────────────
    step(4, TOTAL, "Submitting 5 pulses per steward")

    alice_pulse_ids = []
    for i, domain in enumerate(PULSE_DOMAINS):
        p = client.submit_pulse(
            scarcity_domain=domain,
            description=f"Alice pulse {i+1} — {domain}",
            value_add=PULSE_VALUE,
            steward_key=alice_key,
        )
        alice_pulse_ids.append(p["id"])
        console.print(f"  Alice pulse {i+1}: id={p['id'][:8]}... domain={domain} status={p['status']}")

    bob_pulse_ids = []
    for i, domain in enumerate(PULSE_DOMAINS):
        p = bob_client.submit_pulse(
            scarcity_domain=domain,
            description=f"Bob pulse {i+1} — {domain}",
            value_add=PULSE_VALUE,
            steward_key=bob_key,
        )
        bob_pulse_ids.append(p["id"])
        console.print(f"  Bob   pulse {i+1}: id={p['id'][:8]}... domain={domain} status={p['status']}")

    # ── validate all pulses ───────────────────────────────────────────────────
    step(5, TOTAL, "Validating all 10 pulses (admin)")

    validated = 0
    rejected = 0
    for pulse_id in alice_pulse_ids + bob_pulse_ids:
        try:
            result = client.validate_pulse(pulse_id)
            console.print(f"  ✓ {pulse_id[:8]}... → {result['status']}")
            validated += 1
        except PulserMeshError as e:
            console.print(f"  [yellow]⚠ {pulse_id[:8]}... rejected: {e.detail}[/yellow]")
            rejected += 1

    console.print(f"  Validated: {validated}  Rejected (proximity): {rejected}")

    # ── advance checkpoint ───────────────────────────────────────────────────
    step(6, TOTAL, "Advancing checkpoint")
    cp = client.advance_checkpoint(ta_ref=1.0)
    console.print(f"  Checkpoint index: {cp.get('index')} hash: {cp.get('hash', '')[:16]}...")

    # ── inspect snark fields ──────────────────────────────────────────────────
    step(7, TOTAL, "Inspecting snark fields post-advance")

    alice_id_resp = client.get_identity(alice_id, alice_key)
    bob_id_resp = bob_client.get_identity(bob_id, bob_key)

    console.print("  Alice:")
    assert_field("    pulse_count",     alice_id_resp.get("pulse_count"), 5)
    assert_field(
        "    null_centroid_za",
        alice_id_resp.get("null_centroid_za"),
        "float in [0, 2π)",
        check_fn=lambda v: v is not None and 0.0 <= v < 6.284,
    )
    assert_field(
        "    mission_delta",
        alice_id_resp.get("mission_delta"),
        "float in [0, π]",
        check_fn=lambda v: v is not None and 0.0 <= v <= 3.1416,
    )

    console.print("  Bob:")
    assert_field("    pulse_count", bob_id_resp.get("pulse_count"), 5)
    assert_field(
        "    null_centroid_za",
        bob_id_resp.get("null_centroid_za"),
        "float in [0, 2π)",
        check_fn=lambda v: v is not None and 0.0 <= v < 6.284,
    )
    assert_field(
        "    mission_delta",
        bob_id_resp.get("mission_delta"),
        None,  # Bob has no declared mission
    )

    # ── second checkpoint — stability ─────────────────────────────────────────
    step(8, TOTAL, "Advancing second checkpoint (centroid stability check)")
    cp2 = client.advance_checkpoint(ta_ref=2.0)
    console.print(f"  Checkpoint index: {cp2.get('index')}")

    alice_after = client.get_identity(alice_id, alice_key)
    centroid_1 = alice_id_resp.get("null_centroid_za")
    centroid_2 = alice_after.get("null_centroid_za")
    console.print(f"  Alice centroid after cp1: {centroid_1:.4f}")
    console.print(f"  Alice centroid after cp2: {centroid_2:.4f}  (no new pulses → should be identical)")
    assert_field(
        "    centroid stable across checkpoints with no new pulses",
        abs(centroid_1 - centroid_2) < 1e-6,
        True,
    )

    console.rule("[bold green]All assertions passed[/bold green]")


if __name__ == "__main__":
    try:
        run()
    except AssertionError as e:
        console.print(f"\n[bold red]{e}[/bold red]")
        sys.exit(1)
    except PulserMeshError as e:
        console.print(f"\n[bold red]Server error: {e}[/bold red]")
        sys.exit(1)
