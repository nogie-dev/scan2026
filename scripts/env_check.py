#!/usr/bin/env python3
"""Check the read-only investigation capabilities of the current environment."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen


RPC_ENV_VARS = ("SCAN_RPC_URL", "ETH_RPC_URL", "RPC_URL")
DUNE_MODES = {"auto", "prefer", "required", "off"}


class RpcError(RuntimeError):
    pass


def rpc_call(url: str, method: str, params: list[object]) -> object:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = Request(
        url,
        data=body,
        headers={"content-type": "application/json", "user-agent": "scan2026-readonly/1.0"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except Exception as exc:  # urllib errors differ across Python versions.
        raise RpcError(str(exc)) from exc
    if "error" in payload:
        raise RpcError(str(payload["error"]))
    return payload.get("result")


def quantity(value: object) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise ValueError(f"expected JSON-RPC quantity, got {value!r}")
    return int(value, 16)


def env_rpc_url(cli_value: str | None) -> str | None:
    if cli_value:
        return cli_value
    for name in RPC_ENV_VARS:
        if os.environ.get(name):
            return os.environ[name]
    return None


def dune_state(cli_value: str | None) -> str:
    value = cli_value or os.environ.get("DUNE_MCP_AVAILABLE", "unknown")
    value = value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return "available"
    if value in {"0", "false", "no", "off"}:
        return "unavailable"
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc-url", help="RPC URL; defaults to SCAN_RPC_URL, ETH_RPC_URL, or RPC_URL")
    parser.add_argument("--expected-chain-id", type=lambda value: int(value, 0))
    parser.add_argument("--dune-mode", choices=sorted(DUNE_MODES), default=os.environ.get("DUNE_MODE", "auto"))
    parser.add_argument("--dune-available", choices=("true", "false", "unknown"))
    parser.add_argument("--skip-rpc", action="store_true", help="Only report configuration checks")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    result: dict[str, object] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "dune": {
            "mode": args.dune_mode,
            "mcp": dune_state(args.dune_available),
            "note": "MCP availability is reported, not installed, by this script.",
        },
        "rpc": {"status": "skipped" if args.skip_rpc else "not_checked"},
    }

    if not args.skip_rpc:
        url = env_rpc_url(args.rpc_url)
        if not url:
            result["rpc"] = {"status": "missing", "env_vars": list(RPC_ENV_VARS)}
        else:
            try:
                chain_id = quantity(rpc_call(url, "eth_chainId", []))
                latest_block = quantity(rpc_call(url, "eth_blockNumber", []))
                rpc_result: dict[str, object] = {
                    "status": "ok",
                    "chain_id": chain_id,
                    "latest_block": latest_block,
                }
                if args.expected_chain_id is not None:
                    rpc_result["expected_chain_id"] = args.expected_chain_id
                    rpc_result["chain_id_matches"] = chain_id == args.expected_chain_id
                    if chain_id != args.expected_chain_id:
                        rpc_result["status"] = "chain_id_mismatch"
                result["rpc"] = rpc_result
            except (RpcError, ValueError) as exc:
                result["rpc"] = {"status": "error", "error": str(exc)}

    dune_required_missing = args.dune_mode == "required" and result["dune"]["mcp"] != "available"  # type: ignore[index]
    rpc_failed = result["rpc"]["status"] in {"missing", "error", "chain_id_mismatch"}  # type: ignore[index]
    exit_code = 2 if dune_required_missing or rpc_failed else 0
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
