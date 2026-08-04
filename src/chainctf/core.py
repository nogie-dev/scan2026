"""Core case storage, RPC collection, normalization, verification, and reporting."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.request import Request, urlopen

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


class ChainCTFError(RuntimeError):
    """Base error raised by chainctf."""


class RPCError(ChainCTFError):
    """JSON-RPC request failed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def quantity(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.startswith("0x"):
        return int(value, 16)
    raise ValueError(f"expected an integer or JSON-RPC quantity, got {value!r}")


def normalize_hash(value: str) -> str:
    value = value.strip().lower()
    if not value.startswith("0x") or len(value) != 66:
        raise ValueError(f"invalid transaction hash: {value!r}")
    int(value[2:], 16)
    return value


def normalize_address(value: str) -> str:
    value = value.strip().lower()
    if not value.startswith("0x") or len(value) != 42:
        raise ValueError(f"invalid EVM address: {value!r}")
    int(value[2:], 16)
    return value


def topic_address(topic: str) -> str:
    if not isinstance(topic, str) or not topic.startswith("0x") or len(topic) != 66:
        raise ValueError(f"invalid address topic: {topic!r}")
    return normalize_address("0x" + topic[-40:])


@dataclass(slots=True)
class CaseConfig:
    name: str
    chain_id: int
    rpc_env: str = "SCAN_RPC_URL"
    targets: list[str] = field(default_factory=list)
    reference_block: int | None = None
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CaseConfig":
        return cls(
            name=str(value["name"]),
            chain_id=int(value["chain_id"]),
            rpc_env=str(value.get("rpc_env", "SCAN_RPC_URL")),
            targets=[str(item) for item in value.get("targets", [])],
            reference_block=(
                int(value["reference_block"]) if value.get("reference_block") is not None else None
            ),
            created_at=str(value.get("created_at", utc_now())),
        )


class CaseStore:
    def __init__(self, root: Path):
        self.root = root
        self.config_path = root / "case.json"
        self.raw_transactions = root / "raw" / "transactions"
        self.reports = root / "reports"

    @classmethod
    def create(cls, root: Path, config: CaseConfig) -> "CaseStore":
        if root.exists() and any(root.iterdir()):
            raise ChainCTFError(f"case directory is not empty: {root}")
        store = cls(root)
        store.raw_transactions.mkdir(parents=True, exist_ok=True)
        store.reports.mkdir(parents=True, exist_ok=True)
        store.write_json(store.config_path, asdict(config))
        return store

    def load_config(self) -> CaseConfig:
        if not self.config_path.exists():
            raise ChainCTFError(f"case.json not found under {self.root}")
        return CaseConfig.from_dict(self.read_json(self.config_path))

    def evidence_path(self, tx_hash: str) -> Path:
        return self.raw_transactions / f"{normalize_hash(tx_hash)[2:]}.json"

    def save_evidence(self, tx_hash: str, evidence: dict[str, Any]) -> Path:
        path = self.evidence_path(tx_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.write_json(path, evidence)
        return path

    def load_evidence(self, tx_hash: str) -> dict[str, Any]:
        path = self.evidence_path(tx_hash)
        if not path.exists():
            raise ChainCTFError(f"evidence not found for {tx_hash}; run collect first")
        return self.read_json(path)

    @staticmethod
    def write_json(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def read_json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))


class RPCClient:
    def __init__(self, url: str, *, timeout: float = 30.0, retries: int = 2):
        self.url = url
        self.timeout = timeout
        self.retries = retries
        self._request_id = 0

    @classmethod
    def from_case(cls, config: CaseConfig) -> "RPCClient":
        url = os.environ.get(config.rpc_env)
        if not url:
            raise ChainCTFError(f"RPC URL is missing; set environment variable {config.rpc_env}")
        return cls(url)

    def call(self, method: str, params: list[Any]) -> Any:
        self._request_id += 1
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params}
        ).encode()
        request = Request(
            self.url,
            data=payload,
            headers={"content-type": "application/json", "user-agent": "chainctf/0.1"},
        )
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    result = json.load(response)
                if "error" in result:
                    raise RPCError(f"{method}: {result['error']}")
                return result.get("result")
            except RPCError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.25 * (2**attempt))
        raise RPCError(f"{method}: {last_error}")


def collect_transaction(client: RPCClient, tx_hash: str, *, trace: bool = False) -> dict[str, Any]:
    tx_hash = normalize_hash(tx_hash)
    transaction = client.call("eth_getTransactionByHash", [tx_hash])
    receipt = client.call("eth_getTransactionReceipt", [tx_hash])
    if transaction is None or receipt is None:
        raise ChainCTFError(f"transaction or receipt not found: {tx_hash}")

    chain_id = quantity(client.call("eth_chainId", []))
    block_number = transaction.get("blockNumber")
    block = client.call("eth_getBlockByNumber", [block_number, False]) if block_number else None
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "collected_at": utc_now(),
        "chain_id": chain_id,
        "transaction": transaction,
        "receipt": receipt,
        "block": block,
        "trace": None,
        "trace_error": None,
    }
    if trace:
        try:
            evidence["trace"] = client.call(
                "debug_traceTransaction", [tx_hash, {"tracer": "callTracer"}]
            )
        except RPCError as exc:
            evidence["trace_error"] = str(exc)
    return evidence


def extract_token_transfers(receipt: dict[str, Any] | None) -> list[dict[str, Any]]:
    transfers: list[dict[str, Any]] = []
    if not receipt:
        return transfers
    for log in receipt.get("logs", []):
        topics = log.get("topics") or []
        if len(topics) < 3 or str(topics[0]).lower() != TRANSFER_TOPIC:
            continue
        try:
            amount = int(str(log.get("data", "0x0")), 16)
            transfers.append(
                {
                    "token": normalize_address(str(log["address"])),
                    "from": topic_address(str(topics[1])),
                    "to": topic_address(str(topics[2])),
                    "amount_raw": amount,
                    "log_index": quantity(log.get("logIndex")),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return transfers


def flatten_calls(trace: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(trace, dict):
        return []
    calls: list[dict[str, Any]] = []

    def visit(node: dict[str, Any], path: tuple[int, ...]) -> None:
        input_data = str(node.get("input") or "0x")
        calls.append(
            {
                "path": list(path),
                "depth": len(path),
                "type": node.get("type", "CALL"),
                "from": str(node.get("from", "")).lower() or None,
                "to": str(node.get("to", "")).lower() or None,
                "selector": input_data[:10].lower() if len(input_data) >= 10 else None,
                "value": quantity(node.get("value")) if node.get("value") is not None else 0,
                "gas_used": quantity(node.get("gasUsed")),
                "error": node.get("error"),
            }
        )
        for index, child in enumerate(node.get("calls") or []):
            if isinstance(child, dict):
                visit(child, path + (index,))

    visit(trace, ())
    return calls


def build_dossier(evidence: dict[str, Any]) -> dict[str, Any]:
    tx = evidence.get("transaction") or {}
    receipt = evidence.get("receipt") or {}
    block = evidence.get("block") or {}
    input_data = str(tx.get("input") or "0x")
    return {
        "transaction_hash": str(tx.get("hash", "")).lower(),
        "chain_id": evidence.get("chain_id"),
        "block_number": quantity(tx.get("blockNumber")),
        "block_timestamp": quantity(block.get("timestamp")),
        "from": str(tx.get("from", "")).lower() or None,
        "to": str(tx.get("to", "")).lower() or None,
        "created_contract": str(receipt.get("contractAddress", "")).lower() or None,
        "status": quantity(receipt.get("status")),
        "selector": input_data[:10].lower() if len(input_data) >= 10 else None,
        "value": quantity(tx.get("value")) or 0,
        "gas_used": quantity(receipt.get("gasUsed")),
        "token_transfers": extract_token_transfers(receipt),
        "calls": flatten_calls(evidence.get("trace")),
        "trace_error": evidence.get("trace_error"),
    }


def verify_evidence(config: CaseConfig, evidence: dict[str, Any], tx_hash: str) -> list[dict[str, Any]]:
    expected_hash = normalize_hash(tx_hash)
    tx = evidence.get("transaction") or {}
    receipt = evidence.get("receipt") or {}
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    actual_chain_id = quantity(evidence.get("chain_id"))
    add("chain_id", actual_chain_id == config.chain_id, f"got {actual_chain_id}, expected {config.chain_id}")
    tx_actual = str(tx.get("hash", "")).lower()
    receipt_actual = str(receipt.get("transactionHash", "")).lower()
    add("transaction_hash", tx_actual == expected_hash, f"transaction hash is {tx_actual or 'missing'}")
    add("receipt_hash", receipt_actual == expected_hash, f"receipt hash is {receipt_actual or 'missing'}")
    add(
        "block_number",
        tx.get("blockNumber") is not None and tx.get("blockNumber") == receipt.get("blockNumber"),
        f"transaction={tx.get('blockNumber')}, receipt={receipt.get('blockNumber')}",
    )
    status = quantity(receipt.get("status"))
    add("execution_status", status == 1, f"status={status}")
    add("evidence_schema", evidence.get("schema_version") == 1, f"schema={evidence.get('schema_version')}")
    return checks


def markdown_report(config: CaseConfig, dossier: dict[str, Any], checks: Iterable[dict[str, Any]]) -> str:
    transfers = dossier.get("token_transfers") or []
    calls = dossier.get("calls") or []
    lines = [
        "# chainctf transaction report",
        "",
        f"- Case: `{config.name}`",
        f"- Chain ID: `{dossier.get('chain_id')}`",
        f"- Transaction: `{dossier.get('transaction_hash')}`",
        f"- Block: `{dossier.get('block_number')}`",
        f"- Status: `{dossier.get('status')}`",
        f"- From: `{dossier.get('from')}`",
        f"- To: `{dossier.get('to')}`",
        f"- Selector: `{dossier.get('selector')}`",
        "",
        "## Verification",
        "",
    ]
    for check in checks:
        marker = "PASS" if check["passed"] else "FAIL"
        lines.append(f"- **{marker}** `{check['name']}` — {check['detail']}")

    lines.extend(["", "## ERC-20 transfers", ""])
    if transfers:
        lines.extend(["| Token | From | To | Raw amount |", "| --- | --- | --- | ---: |"])
        for item in transfers:
            lines.append(
                f"| `{item['token']}` | `{item['from']}` | `{item['to']}` | `{item['amount_raw']}` |"
            )
    else:
        lines.append("No ERC-20 `Transfer` logs were decoded.")

    lines.extend(["", "## Call trace", ""])
    if calls:
        lines.extend(["| Path | Type | From | To | Selector | Error |", "| --- | --- | --- | --- | --- | --- |"])
        for item in calls:
            path = ".".join(str(value) for value in item["path"]) or "root"
            lines.append(
                f"| `{path}` | `{item['type']}` | `{item['from']}` | `{item['to']}` | "
                f"`{item['selector']}` | `{item['error'] or ''}` |"
            )
    elif dossier.get("trace_error"):
        lines.append(f"Trace unavailable: `{dossier['trace_error']}`")
    else:
        lines.append("Trace was not collected.")
    lines.append("")
    return "\n".join(lines)
