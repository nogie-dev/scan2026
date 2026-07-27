#!/usr/bin/env python3
"""Collect read-only EVM logs and transaction evidence as JSON."""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


RPC_ENV_VARS = ("SCAN_RPC_URL", "ETH_RPC_URL", "RPC_URL")


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
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except Exception as exc:
        raise RpcError(str(exc)) from exc
    if "error" in payload:
        raise RpcError(str(payload["error"]))
    return payload.get("result")


def quantity(value: object) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise ValueError(f"expected JSON-RPC quantity, got {value!r}")
    return int(value, 16)


def hex_quantity(value: str) -> str:
    return hex(int(value, 0))


def env_rpc_url(cli_value: str | None) -> str | None:
    if cli_value:
        return cli_value
    for name in RPC_ENV_VARS:
        if os.environ.get(name):
            return os.environ[name]
    return None


def safe_url(url: str) -> str:
    """Keep the endpoint identity without recording query-string API keys."""
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def block_number(item: dict[str, object], field: str) -> int:
    return quantity(item.get(field))


def log_sort_key(item: dict[str, object]) -> tuple[int, int, int]:
    return (
        block_number(item, "blockNumber"),
        block_number(item, "transactionIndex"),
        block_number(item, "logIndex"),
    )


def dedupe_logs(logs: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return one transaction record per tx hash while retaining event counts."""
    groups: dict[str, dict[str, object]] = {}
    for item in sorted(logs, key=log_sort_key):
        tx_hash = str(item["transactionHash"]).lower()
        group = groups.setdefault(
            tx_hash,
            {
                "transaction_hash": item["transactionHash"],
                "block_number": block_number(item, "blockNumber"),
                "transaction_index": block_number(item, "transactionIndex"),
                "first_log_index": block_number(item, "logIndex"),
                "log_count": 0,
            },
        )
        group["log_count"] = int(group["log_count"]) + 1
    return sorted(groups.values(), key=lambda item: (item["block_number"], item["transaction_index"]))


def collect_transaction(url: str, tx_hash: str, mode: str) -> dict[str, object]:
    record: dict[str, object] = {"transaction_hash": tx_hash}
    for name, method in (("transaction", "eth_getTransactionByHash"), ("receipt", "eth_getTransactionReceipt")):
        try:
            record[name] = rpc_call(url, method, [tx_hash])
        except RpcError as exc:
            record[f"{name}_error"] = str(exc)
    if mode == "trace":
        try:
            record["trace"] = rpc_call(url, "debug_traceTransaction", [tx_hash, {"tracer": "callTracer"}])
        except RpcError as exc:
            record["trace_error"] = str(exc)
    return record


def self_test() -> None:
    assert quantity("0x10") == 16
    logs = [
        {"transactionHash": "0xB", "blockNumber": "0x2", "transactionIndex": "0x1", "logIndex": "0x2"},
        {"transactionHash": "0xA", "blockNumber": "0x1", "transactionIndex": "0x3", "logIndex": "0x0"},
        {"transactionHash": "0xB", "blockNumber": "0x2", "transactionIndex": "0x1", "logIndex": "0x4"},
    ]
    deduped = dedupe_logs(logs)
    assert [item["transaction_hash"] for item in deduped] == ["0xA", "0xB"]
    assert deduped[1]["log_count"] == 2
    print("self-test: ok")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc-url", help="RPC URL; defaults to SCAN_RPC_URL, ETH_RPC_URL, or RPC_URL")
    parser.add_argument("--expected-chain-id", type=lambda value: int(value, 0))
    parser.add_argument("--from-block", help="Inclusive block number, e.g. 0x100 or 256")
    parser.add_argument("--to-block", help="Inclusive block number, e.g. 0x200 or 512")
    parser.add_argument("--address", action="append", help="Log address; may be repeated")
    parser.add_argument("--topic0", help="First event topic")
    parser.add_argument("--tx", action="append", default=[], help="Transaction hash; may be repeated")
    parser.add_argument("--tx-file", type=Path, help="File containing one transaction hash per line")
    parser.add_argument("--collect", choices=("none", "receipt", "trace"), default="none")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", default="-", help="Output JSON path, or - for stdout")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if args.workers < 1:
        parser.error("--workers must be at least 1")

    url = env_rpc_url(args.rpc_url)
    if not url:
        parser.error("RPC URL is required via --rpc-url, SCAN_RPC_URL, ETH_RPC_URL, or RPC_URL")

    has_range = args.from_block is not None or args.to_block is not None
    if has_range and (args.from_block is None or args.to_block is None):
        parser.error("--from-block and --to-block must be supplied together")
    if has_range and not args.address and not args.topic0:
        parser.error("log collection requires --address or --topic0")
    if has_range and int(args.from_block, 0) > int(args.to_block, 0):
        parser.error("--from-block must not exceed --to-block")

    chain_id = quantity(rpc_call(url, "eth_chainId", []))
    latest_block = quantity(rpc_call(url, "eth_blockNumber", []))
    if args.expected_chain_id is not None and chain_id != args.expected_chain_id:
        parser.error(f"chain ID mismatch: got {chain_id}, expected {args.expected_chain_id}")

    logs: list[dict[str, object]] = []
    if has_range:
        log_filter: dict[str, object] = {
            "fromBlock": hex_quantity(args.from_block),
            "toBlock": hex_quantity(args.to_block),
        }
        if args.address:
            log_filter["address"] = args.address[0] if len(args.address) == 1 else args.address
        if args.topic0:
            log_filter["topics"] = [args.topic0]
        result = rpc_call(url, "eth_getLogs", [log_filter])
        if not isinstance(result, list):
            raise RpcError("eth_getLogs returned a non-list result")
        logs = result

    tx_hashes = list(args.tx)
    if args.tx_file:
        tx_hashes.extend(
            line.strip() for line in args.tx_file.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")
        )
    tx_hashes.extend(item["transaction_hash"] for item in dedupe_logs(logs))
    tx_hashes = list(dict.fromkeys(str(item).lower() for item in tx_hashes))

    transactions: list[dict[str, object]] = []
    if args.collect != "none" and tx_hashes:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(collect_transaction, url, tx_hash, args.collect): tx_hash for tx_hash in tx_hashes}
            for future in as_completed(futures):
                transactions.append(future.result())
        transactions.sort(key=lambda item: item["transaction_hash"])

    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "rpc": {"url": safe_url(url), "chain_id": chain_id, "latest_block": latest_block},
        "request": {
            "from_block": int(args.from_block, 0) if args.from_block is not None else None,
            "to_block": int(args.to_block, 0) if args.to_block is not None else None,
            "addresses": args.address or [],
            "topic0": args.topic0,
            "transaction_hashes": tx_hashes,
            "collect": args.collect,
        },
        "logs": logs,
        "deduped_transactions": dedupe_logs(logs),
        "transactions": transactions,
    }
    encoded = json.dumps(output, indent=2 if args.pretty else None, sort_keys=True)
    if args.output == "-":
        print(encoded)
    else:
        Path(args.output).write_text(encoded + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RpcError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
