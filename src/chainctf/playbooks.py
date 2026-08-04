"""Reusable investigation playbooks built on top of cached chainctf evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .core import (
    CaseConfig,
    CaseStore,
    ChainCTFError,
    RPCClient,
    RPCError,
    collect_transaction,
    normalize_address,
    quantity,
    topic_address,
)

UPGRADED_TOPIC = "0xbc7cd75a20ee27fd9adebab32041f755214dbc6bffa90cc0225b39da2e5c2d3b"
IMPLEMENTATION_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
UPGRADE_TO_AND_CALL_SELECTOR = "0x4f1ef286"
PROXY_ADMIN_UPGRADE_AND_CALL_SELECTOR = "0x9623609d"


def _block_tag(value: int) -> str:
    if value < 0:
        raise ValueError("block number must not be negative")
    return hex(value)


def _log_sort_key(log: dict[str, Any]) -> tuple[int, int, int]:
    return (
        quantity(log.get("blockNumber")) or 0,
        quantity(log.get("transactionIndex")) or 0,
        quantity(log.get("logIndex")) or 0,
    )


def _fetch_logs_range(
    client: RPCClient,
    proxy: str,
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    """Fetch one log range and bisect providers' range-limit failures."""
    params = [{
        "address": proxy,
        "fromBlock": _block_tag(start),
        "toBlock": _block_tag(end),
        "topics": [UPGRADED_TOPIC],
    }]
    try:
        result = client.call("eth_getLogs", params)
    except RPCError:
        if start >= end:
            raise
        midpoint = (start + end) // 2
        return _fetch_logs_range(client, proxy, start, midpoint) + _fetch_logs_range(
            client, proxy, midpoint + 1, end
        )
    if not isinstance(result, list):
        raise ChainCTFError("eth_getLogs returned a non-list result")
    return [item for item in result if isinstance(item, dict)]


def find_upgrade_logs(
    client: RPCClient,
    proxy: str,
    *,
    from_block: int = 0,
    to_block: int | None = None,
    chunk_size: int = 100_000,
) -> list[dict[str, Any]]:
    proxy = normalize_address(proxy)
    if from_block < 0:
        raise ValueError("from_block must not be negative")
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    latest = quantity(client.call("eth_blockNumber", []))
    if latest is None:
        raise ChainCTFError("eth_blockNumber returned no result")
    end = latest if to_block is None else to_block
    if end < from_block:
        raise ValueError("to_block must not be smaller than from_block")
    if end > latest:
        raise ValueError(f"to_block {end} exceeds latest block {latest}")

    logs: list[dict[str, Any]] = []
    cursor = from_block
    while cursor <= end:
        chunk_end = min(cursor + chunk_size - 1, end)
        logs.extend(_fetch_logs_range(client, proxy, cursor, chunk_end))
        cursor = chunk_end + 1
    return sorted(logs, key=_log_sort_key)


def _decode_address_word(data: bytes, word_index: int) -> str:
    start = word_index * 32
    word = data[start : start + 32]
    if len(word) != 32:
        raise ValueError("calldata is shorter than the requested address word")
    return normalize_address("0x" + word[-20:].hex())


def _decode_dynamic_bytes(data: bytes, offset_word_index: int) -> bytes:
    offset_start = offset_word_index * 32
    offset_word = data[offset_start : offset_start + 32]
    if len(offset_word) != 32:
        raise ValueError("calldata is shorter than the dynamic offset word")
    offset = int.from_bytes(offset_word, "big")
    if offset % 32 != 0:
        raise ValueError("dynamic bytes offset is not word-aligned")
    length_word = data[offset : offset + 32]
    if len(length_word) != 32:
        raise ValueError("dynamic bytes length is missing")
    length = int.from_bytes(length_word, "big")
    payload = data[offset + 32 : offset + 32 + length]
    if len(payload) != length:
        raise ValueError("dynamic bytes payload is truncated")
    return payload


def decode_upgrade_call(calldata: str, *, expected_proxy: str | None = None) -> dict[str, Any] | None:
    """Decode OpenZeppelin proxy or ProxyAdmin upgrade-and-call calldata."""
    if not isinstance(calldata, str) or not calldata.startswith("0x") or len(calldata) < 10:
        return None
    try:
        raw = bytes.fromhex(calldata[2:])
    except ValueError:
        return None
    selector = "0x" + raw[:4].hex()
    args = raw[4:]
    try:
        if selector == UPGRADE_TO_AND_CALL_SELECTOR:
            implementation = _decode_address_word(args, 0)
            payload = _decode_dynamic_bytes(args, 1)
            return {
                "kind": "proxy.upgradeToAndCall",
                "selector": selector,
                "proxy": normalize_address(expected_proxy) if expected_proxy else None,
                "implementation": implementation,
                "call_data": "0x" + payload.hex(),
                "implementation_selector": "0x" + payload[:4].hex() if len(payload) >= 4 else None,
            }
        if selector == PROXY_ADMIN_UPGRADE_AND_CALL_SELECTOR:
            proxy = _decode_address_word(args, 0)
            implementation = _decode_address_word(args, 1)
            payload = _decode_dynamic_bytes(args, 2)
            if expected_proxy and proxy != normalize_address(expected_proxy):
                return None
            return {
                "kind": "proxy_admin.upgradeAndCall",
                "selector": selector,
                "proxy": proxy,
                "implementation": implementation,
                "call_data": "0x" + payload.hex(),
                "implementation_selector": "0x" + payload[:4].hex() if len(payload) >= 4 else None,
            }
    except ValueError:
        return None
    return None


def _iter_trace_nodes(trace: dict[str, Any] | None) -> Iterable[dict[str, Any]]:
    if not isinstance(trace, dict):
        return
    stack = [trace]
    while stack:
        node = stack.pop()
        yield node
        children = [item for item in (node.get("calls") or []) if isinstance(item, dict)]
        stack.extend(reversed(children))


def _find_upgrade_call(
    evidence: dict[str, Any], proxy: str, implementation: str
) -> dict[str, Any] | None:
    tx = evidence.get("transaction") or {}
    candidates: list[tuple[str | None, str]] = [
        (str(tx.get("to", "")).lower() or None, str(tx.get("input") or "0x"))
    ]
    for node in _iter_trace_nodes(evidence.get("trace")):
        candidates.append((str(node.get("to", "")).lower() or None, str(node.get("input") or "0x")))

    for to_address, calldata in candidates:
        decoded = decode_upgrade_call(calldata, expected_proxy=proxy)
        if not decoded:
            continue
        if decoded["implementation"] != implementation:
            continue
        if decoded["kind"] == "proxy.upgradeToAndCall" and to_address not in {None, proxy}:
            continue
        decoded["call_target"] = to_address
        return decoded
    return None


def _find_delegatecall_selector(
    evidence: dict[str, Any], implementation: str
) -> str | None:
    for node in _iter_trace_nodes(evidence.get("trace")):
        if str(node.get("type", "")).upper() != "DELEGATECALL":
            continue
        if str(node.get("to", "")).lower() != implementation:
            continue
        input_data = str(node.get("input") or "0x").lower()
        if len(input_data) >= 10:
            return input_data[:10]
    return None


def _storage_address(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith("0x"):
        return None
    raw = value[2:].rjust(64, "0")
    try:
        return normalize_address("0x" + raw[-40:])
    except ValueError:
        return None


def run_proxy_upgrade_playbook(
    client: RPCClient,
    store: CaseStore,
    config: CaseConfig,
    proxy: str,
    *,
    from_block: int = 0,
    to_block: int | None = None,
    latest: bool = True,
) -> dict[str, Any]:
    proxy = normalize_address(proxy)
    logs = find_upgrade_logs(
        client,
        proxy,
        from_block=from_block,
        to_block=to_block,
    )
    if not logs:
        raise ChainCTFError("no Upgraded(address) event was found for the selected range")
    selected = logs[-1] if latest else logs[0]
    topics = selected.get("topics") or []
    if len(topics) < 2:
        raise ChainCTFError("selected Upgraded event does not contain an implementation topic")
    implementation = topic_address(str(topics[1]))
    tx_hash = str(selected.get("transactionHash", "")).lower()
    block_number = quantity(selected.get("blockNumber"))
    if block_number is None:
        raise ChainCTFError("selected Upgraded event is missing blockNumber")

    evidence = collect_transaction(client, tx_hash, trace=True)
    evidence_path = store.save_evidence(tx_hash, evidence)
    before_raw = client.call(
        "eth_getStorageAt", [proxy, IMPLEMENTATION_SLOT, _block_tag(max(block_number - 1, 0))]
    )
    after_raw = client.call(
        "eth_getStorageAt", [proxy, IMPLEMENTATION_SLOT, _block_tag(block_number)]
    )
    before_implementation = _storage_address(before_raw)
    after_implementation = _storage_address(after_raw)

    upgrade_call = _find_upgrade_call(evidence, proxy, implementation)
    nested_selector = upgrade_call.get("implementation_selector") if upgrade_call else None
    trace_selector = _find_delegatecall_selector(evidence, implementation)
    if nested_selector is None:
        nested_selector = trace_selector

    receipt = evidence.get("receipt") or {}
    checks = [
        {
            "name": "event_topic",
            "passed": str(topics[0]).lower() == UPGRADED_TOPIC,
            "detail": str(topics[0]).lower(),
        },
        {
            "name": "execution_status",
            "passed": quantity(receipt.get("status")) == 1,
            "detail": f"status={quantity(receipt.get('status'))}",
        },
        {
            "name": "implementation_after",
            "passed": after_implementation == implementation,
            "detail": f"storage={after_implementation}, event={implementation}",
        },
        {
            "name": "implementation_changed",
            "passed": before_implementation is not None and before_implementation != after_implementation,
            "detail": f"before={before_implementation}, after={after_implementation}",
        },
        {
            "name": "implementation_call_selector",
            "passed": nested_selector is not None,
            "detail": f"selector={nested_selector}",
        },
    ]
    if upgrade_call and trace_selector:
        checks.append({
            "name": "trace_selector_matches",
            "passed": upgrade_call.get("implementation_selector") == trace_selector,
            "detail": (
                f"calldata={upgrade_call.get('implementation_selector')}, trace={trace_selector}"
            ),
        })

    return {
        "playbook": "proxy-upgrade",
        "case": config.name,
        "proxy": proxy,
        "range": {"from_block": from_block, "to_block": to_block},
        "upgrade_events_found": len(logs),
        "selection": "latest" if latest else "earliest",
        "transaction_hash": tx_hash,
        "block_number": block_number,
        "implementation_before": before_implementation,
        "implementation_after": after_implementation,
        "event_implementation": implementation,
        "upgrade_call": upgrade_call,
        "trace_implementation_selector": trace_selector,
        "implementation_selector": nested_selector,
        "flag": f"SCAN2024{{{nested_selector}}}" if nested_selector else None,
        "evidence_path": str(evidence_path),
        "checks": checks,
        "passed": all(item["passed"] for item in checks),
    }


def proxy_upgrade_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# chainctf proxy upgrade report",
        "",
        f"- Case: `{result['case']}`",
        f"- Proxy: `{result['proxy']}`",
        f"- Selection: `{result['selection']}`",
        f"- Upgrade events found: `{result['upgrade_events_found']}`",
        f"- Transaction: `{result['transaction_hash']}`",
        f"- Block: `{result['block_number']}`",
        f"- Previous implementation: `{result['implementation_before']}`",
        f"- New implementation: `{result['implementation_after']}`",
        f"- Implementation selector: `{result['implementation_selector']}`",
        f"- Flag candidate: `{result['flag']}`",
        "",
        "## Verification",
        "",
    ]
    for check in result["checks"]:
        marker = "PASS" if check["passed"] else "FAIL"
        lines.append(f"- **{marker}** `{check['name']}` — {check['detail']}")
    lines.append("")
    return "\n".join(lines)


def write_proxy_upgrade_report(
    store: CaseStore, result: dict[str, Any], output: str | None = None
) -> Path:
    path = Path(output) if output else store.reports / "proxy-upgrade.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(proxy_upgrade_markdown(result), encoding="utf-8")
    return path
