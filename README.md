# pulsermesh-client

Dev client and integration test scripts for the [Pulser Mesh server](https://github.com/khala-code/pulsermesh-server).

Not a published SDK — this is a local development tool for scripted integration testing while the server API is pre-release.

## Setup

```bash
pip install -r requirements.txt
```

## Configuration

All scripts read from environment variables:

| Variable | Default | Description |
|---|---|---|
| `PULSERMESH_BASE_URL` | `http://localhost:8000` | Server base URL |
| `PULSERMESH_ADMIN_KEY` | *(required)* | Node admin API key for validate/checkpoint calls |

Export them before running any script:

```bash
export PULSERMESH_BASE_URL=http://localhost:8000
export PULSERMESH_ADMIN_KEY=your-node-admin-key
```

## Scripts

### `scripts/smoke_test.py`

Full lifecycle test: register two stewards (one with domains, one without), submit and validate 5 pulses each, advance a checkpoint, then inspect snark fields. Prints a summary table.

```bash
python scripts/smoke_test.py
```

Expected output when everything is working:

```
[1/7] Registering stewards...
  Alice (with domains: water, energy)  api_key=pm_...
  Bob   (no domains)                   api_key=pm_...
[2/7] Checking baseline snark fields (expect all None)...
  Alice: mission_vector_za=1.2566, null_centroid_za=None, mission_delta=None, pulse_count=0 ✓
  Bob:   mission_vector_za=None,   null_centroid_za=None, mission_delta=None, pulse_count=0 ✓
[3/7] Submitting 5 pulses each...
  Submitted 10 pulses
[4/7] Validating all pulses (admin key)...
  Validated 10 pulses
[5/7] Advancing checkpoint...
  Checkpoint index: 1
[6/7] Inspecting snark fields post-advance...
  Alice: mission_vector_za=1.2566, null_centroid_za=1.1803, mission_delta=0.0763, pulse_count=5 ✓
  Bob:   mission_vector_za=None,   null_centroid_za=0.9817, mission_delta=None,   pulse_count=5 ✓
[7/7] All assertions passed.
```

### `scripts/snark_watch.py`

Advances N checkpoints in sequence and prints how snark fields evolve. Useful for observing centroid convergence over time.

```bash
python scripts/snark_watch.py --steward-id <id> --checkpoints 10
```

## Library

`pulsermesh/client.py` is a thin `httpx` wrapper you can import directly:

```python
from pulsermesh.client import PulserMeshClient

client = PulserMeshClient(base_url="http://localhost:8000", admin_key="...")
steward = client.register_steward("Alice", domains=["water", "energy"])
print(steward["api_key"])
```
