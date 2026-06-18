# pulsermesh-client

Dev client and integration test scripts for the [Pulser Mesh server](https://github.com/khala-code/pulsermesh-server).

Not a published SDK — this is a local development tool for scripted integration testing while the server API is pre-release.

## Prerequisites

- Python 3.11+ (3.12 also works)
- The Pulser Mesh server running locally (see the server repo for setup)
- Your node admin API key (set during server initialisation)

---

## Environment Setup

Choose one of the three options below. All three result in the same working state.

### Option A — Conda (Miniforge / Anaconda)

Recommended if you already have Miniforge or Anaconda installed.

**macOS / Linux — Terminal:**
```bash
conda create -n pulsermesh python=3.11 -y
conda activate pulsermesh
```

**Windows — open Miniforge Prompt** (not PowerShell):
```bat
conda create -n pulsermesh python=3.11 -y
conda activate pulsermesh
```

Then clone and install:
```bash
git clone https://github.com/khala-code/pulsermesh-client.git
cd pulsermesh-client
pip install -r requirements.txt
```

> The two dependencies (`httpx`, `rich`) are pure Python — no conda channel needed, `pip` is fine.

---

### Option B — venv (stdlib, no extra tools)

Recommended if you just want a lightweight isolated environment without conda.

**macOS / Linux:**
```bash
git clone https://github.com/khala-code/pulsermesh-client.git
cd pulsermesh-client
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/khala-code/pulsermesh-client.git
cd pulsermesh-client
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> If PowerShell blocks the activate script with an execution policy error, run:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

---

### Option C — No virtual environment

If you just want to run a quick test and don't mind installing into your global Python:
```bash
pip install -r requirements.txt
```

---

## Configuration

All scripts read from environment variables:

| Variable | Default | Description |
|---|---|---|
| `PULSERMESH_BASE_URL` | `http://localhost:8000` | Server base URL |
| `PULSERMESH_ADMIN_KEY` | *(required)* | Node admin API key for validate/checkpoint calls |

### Using a `.env` file (recommended)

Create a `.env` file in the repo root — it is already in `.gitignore` so it won't be committed:

```
PULSERMESH_BASE_URL=http://localhost:8000
PULSERMESH_ADMIN_KEY=your-node-admin-key
```

Then install `python-dotenv`:

```bash
pip install python-dotenv
```

And load it at the top of any script or notebook:

```python
from dotenv import load_dotenv
load_dotenv()  # reads .env from the current directory
```

Both `smoke_test.py` and `snark_watch.py` call `load_dotenv()` automatically if `python-dotenv` is installed, so you don't need to add anything — just create the `.env` file and run.

### Setting variables manually (alternative)

**macOS / Linux:**
```bash
export PULSERMESH_BASE_URL=http://localhost:8000
export PULSERMESH_ADMIN_KEY=your-node-admin-key
```

**Windows (Miniforge Prompt or cmd):**
```bat
set PULSERMESH_BASE_URL=http://localhost:8000
set PULSERMESH_ADMIN_KEY=your-node-admin-key
```

**Windows (PowerShell):**
```powershell
$env:PULSERMESH_BASE_URL = "http://localhost:8000"
$env:PULSERMESH_ADMIN_KEY = "your-node-admin-key"
```

Manually set variables are session-scoped — you'll need to re-set them each time you open a new terminal.

---

## Scripts

### `scripts/smoke_test.py`

Full lifecycle test: register two stewards (one with domains, one without), submit and validate 5 pulses each, advance a checkpoint, then inspect snark fields. Prints a summary with pass/fail per assertion.

```bash
python scripts/smoke_test.py
```

Expected output when everything is working:

```
[1/8] Health check
[2/8] Registering stewards
  Alice  id=a1b2c3d4...  api_key=pm_abc12345...
         mission_vector_za=1.2566
  Bob    id=e5f6g7h8...  api_key=pm_xyz98765...
[3/8] Baseline snark fields (expect nulls except mission_vector_za for Alice)
  Alice:
    ✓ null_centroid_za: None
    ✓ mission_delta: None
    ✓ pulse_count: 0
    ✓ mission_vector_za: 1.2566
  Bob:
    ✓ null_centroid_za: None
    ✓ mission_vector_za: None
    ✓ pulse_count: 0
[4/8] Submitting 5 pulses per steward
[5/8] Validating all 10 pulses (admin)
  Validated: 10  Rejected (proximity): 0
[6/8] Advancing checkpoint
  Checkpoint index: 1  hash: 3f9a1c2b...
[7/8] Inspecting snark fields post-advance
  Alice:
    ✓ pulse_count: 5
    ✓ null_centroid_za: 1.1803
    ✓ mission_delta: 0.0763
  Bob:
    ✓ pulse_count: 5
    ✓ null_centroid_za: 0.9817
    ✓ mission_delta: None
[8/8] Advancing second checkpoint (centroid stability check)
  Alice centroid after cp1: 1.1803
  Alice centroid after cp2: 1.1803  (no new pulses → should be identical)
    ✓ centroid stable across checkpoints with no new pulses: True
──────────────── All assertions passed ────────────────
```

---

### `scripts/snark_watch.py`

Advances N checkpoints in sequence and prints how snark fields evolve at each step. Useful for observing centroid convergence and PLL behaviour over time.

```bash
# Register a fresh steward automatically and watch over 15 checkpoints
python scripts/snark_watch.py --checkpoints 15

# Watch an existing steward
python scripts/snark_watch.py --steward-id <uuid> --steward-key pm_... --checkpoints 10

# Control how many seed pulses are created for the auto-registered steward
python scripts/snark_watch.py --checkpoints 20 --seed-pulses 12
```

Example output:

```
checkpoint      pulse_count     null_centroid   mission_vec     mission_delta
--------------------------------------------------------------------------------
  1             8               1.2314          1.2566          0.0252
  2             8               1.2401          1.2566          0.0165
  3             8               1.2448          1.2566          0.0118
  ...
```

---

## Library

`pulsermesh/client.py` is a thin `httpx` wrapper you can import directly in your own scripts or a Jupyter notebook:

```python
from dotenv import load_dotenv
load_dotenv()

from pulsermesh.client import PulserMeshClient

client = PulserMeshClient()  # reads base_url and admin_key from env
steward = client.register_steward("Alice", domains=["water", "energy"])
print(steward["api_key"])    # stored automatically on client.steward_key

pulse = client.submit_pulse("water", "Test contribution", value_add=1.0)
client.validate_pulse(pulse["id"])
client.advance_checkpoint(ta_ref=1.0)

identity = client.get_identity(steward["id"])
print(identity["null_centroid_za"])   # populated after first checkpoint with ≥5 pulses
print(identity["mission_delta"])      # angular gap between declared mission and centroid
```

### Using in a Jupyter / conda notebook

```bash
conda activate pulsermesh
pip install jupyter ipykernel
python -m ipykernel install --user --name pulsermesh --display-name "Pulser Mesh"
jupyter notebook
```

Then select the **Pulser Mesh** kernel in the notebook UI. The client can be imported directly — no installation step needed since the package is not published to PyPI yet.
