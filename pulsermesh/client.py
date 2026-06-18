"""
pulsermesh/client.py — Thin httpx wrapper for the Pulser Mesh server API.

Covers every endpoint currently implemented:
  - Health
  - Node info
  - Steward registration and identity
  - Pulse submit, validate, list
  - Checkpoint advance and current state

Auth model:
  - Steward calls (submit pulse, get own pulses, get own identity) use
    the steward's pm_ API key in the X-API-Key header.
  - Admin calls (validate pulse, advance checkpoint, node info) use the
    node admin key.
  - The client holds both: admin_key always present, steward_key set
    after register_steward() or via set_steward_key().
"""
from __future__ import annotations
import os
from typing import Any
import httpx


DEFAULT_BASE_URL = "http://localhost:8000"


class PulserMeshError(Exception):
    """Raised when the server returns a non-2xx response."""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class PulserMeshClient:
    """
    Synchronous client for the Pulser Mesh server API.

    Parameters
    ----------
    base_url : str
        Server base URL, e.g. "http://localhost:8000".
        Defaults to PULSERMESH_BASE_URL env var or http://localhost:8000.
    admin_key : str
        Node admin API key. Required for validate/checkpoint/node calls.
        Defaults to PULSERMESH_ADMIN_KEY env var.
    steward_key : str | None
        Steward pm_ key. Set automatically after register_steward().
        Also settable via set_steward_key().
    """

    def __init__(
        self,
        base_url: str | None = None,
        admin_key: str | None = None,
        steward_key: str | None = None,
        timeout: float = 10.0,
    ):
        self.base_url = (base_url or os.environ.get("PULSERMESH_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.admin_key = admin_key or os.environ.get("PULSERMESH_ADMIN_KEY") or ""
        self.steward_key = steward_key
        self._http = httpx.Client(timeout=timeout)

    def set_steward_key(self, key: str) -> None:
        self.steward_key = key

    # ── internal ──────────────────────────────────────────────────────────────

    def _admin_headers(self) -> dict:
        return {"X-API-Key": self.admin_key}

    def _steward_headers(self) -> dict:
        if not self.steward_key:
            raise RuntimeError("No steward key set. Call register_steward() first or set_steward_key().")
        return {"X-API-Key": self.steward_key}

    def _check(self, resp: httpx.Response) -> dict:
        if not resp.is_success:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise PulserMeshError(resp.status_code, detail)
        return resp.json()

    def _get(self, path: str, headers: dict) -> dict:
        return self._check(self._http.get(f"{self.base_url}{path}", headers=headers))

    def _post(self, path: str, headers: dict, body: dict | None = None) -> dict:
        return self._check(self._http.post(f"{self.base_url}{path}", headers=headers, json=body or {}))

    # ── health ────────────────────────────────────────────────────────────────

    def health(self) -> dict:
        """GET /health — no auth required."""
        return self._check(self._http.get(f"{self.base_url}/health"))

    # ── node ──────────────────────────────────────────────────────────────────

    def node_info(self) -> dict:
        """GET /node — returns node identity and current Za."""
        return self._get("/node", self._admin_headers())

    # ── stewards ──────────────────────────────────────────────────────────────

    def register_steward(
        self,
        name: str,
        domains: list[str] | None = None,
        domain_weights: dict[str, float] | None = None,
        oa: float = 1.0,
        za: float = 0.0,
        ta: float = 0.0,
    ) -> dict:
        """
        POST /stewards — register a new steward.

        Sets self.steward_key to the returned api_key automatically.
        Returns the full registration response dict.
        """
        body: dict[str, Any] = {
            "name": name,
            "position": {"oa": oa, "za": za, "ta": ta},
        }
        if domains:
            body["domains"] = domains
        if domain_weights:
            body["domain_weights"] = domain_weights

        resp = self._post("/stewards", self._admin_headers(), body)
        # Store the steward key so subsequent steward-auth calls work immediately
        api_key = resp.get("api_key")
        if api_key:
            self.steward_key = api_key
        return resp

    def get_identity(
        self,
        steward_id: str,
        steward_key: str | None = None,
    ) -> dict:
        """
        GET /stewards/{steward_id}/identity

        Uses steward_key if provided, else self.steward_key.
        Returns identity dict including snark fields:
          mission_vector_za, null_centroid_za, mission_delta, pulse_count.
        """
        key = steward_key or self.steward_key
        if not key:
            raise RuntimeError("No steward key available.")
        headers = {"X-API-Key": key}
        return self._get(f"/stewards/{steward_id}/identity", headers)

    # ── pulses ────────────────────────────────────────────────────────────────

    def submit_pulse(
        self,
        scarcity_domain: str,
        description: str,
        value_add: float,
        steward_key: str | None = None,
    ) -> dict:
        """
        POST /pulses/submit — submit a new pulse.

        Uses steward_key if provided, else self.steward_key.
        Returns the created pulse dict.
        """
        key = steward_key or self.steward_key
        if not key:
            raise RuntimeError("No steward key available.")
        return self._post(
            "/pulses/submit",
            {"X-API-Key": key},
            {
                "scarcity_domain": scarcity_domain,
                "description": description,
                "value_add": value_add,
            },
        )

    def validate_pulse(self, pulse_id: str) -> dict:
        """
        POST /pulses/{pulse_id}/validate — validate a pending pulse.

        Requires admin key.
        """
        return self._post(f"/pulses/{pulse_id}/validate", self._admin_headers())

    def get_pulse(self, pulse_id: str) -> dict:
        """GET /pulses/{pulse_id} — fetch a pulse by ID."""
        return self._get(f"/pulses/{pulse_id}", self._admin_headers())

    def get_my_pulses(self, steward_key: str | None = None) -> list:
        """GET /pulses/mine — list pulses for the current steward."""
        key = steward_key or self.steward_key
        if not key:
            raise RuntimeError("No steward key available.")
        resp = self._check(self._http.get(f"{self.base_url}/pulses/mine", headers={"X-API-Key": key}))
        return resp  # list

    # ── checkpoint ────────────────────────────────────────────────────────────

    def current_checkpoint(self) -> dict:
        """GET /checkpoint — return current checkpoint state."""
        return self._get("/checkpoint", self._admin_headers())

    def advance_checkpoint(self, ta_ref: float = 1.0) -> dict:
        """
        POST /checkpoint/advance — advance the mesh clock.

        Triggers snark field recomputation for all stewards.
        Requires admin key.
        """
        return self._post("/checkpoint/advance", self._admin_headers(), {"ta_ref": ta_ref})

    # ── context manager support ───────────────────────────────────────────────

    def __enter__(self) -> "PulserMeshClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self._http.close()

    def close(self) -> None:
        self._http.close()
