from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chainctf.core import CaseConfig, CaseStore
from chainctf.playbooks import (
    IMPLEMENTATION_SLOT,
    UPGRADED_TOPIC,
    decode_upgrade_call,
    run_proxy_upgrade_playbook,
)

PROXY = "0x" + "11" * 20
ADMIN = "0x" + "22" * 20
OLD_IMPL = "0x" + "33" * 20
NEW_IMPL = "0x" + "44" * 20
TX_HASH = "0x" + "55" * 32
NESTED_SELECTOR = "0xdeadbeef"


def address_word(address: str) -> bytes:
    return bytes.fromhex("00" * 12 + address[2:])


def encode_upgrade_to_and_call(implementation: str, payload: bytes) -> str:
    selector = bytes.fromhex("4f1ef286")
    args = address_word(implementation)
    args += (64).to_bytes(32, "big")
    args += len(payload).to_bytes(32, "big")
    args += payload + b"\x00" * ((32 - len(payload) % 32) % 32)
    return "0x" + (selector + args).hex()


def storage_word(address: str) -> str:
    return "0x" + "00" * 12 + address[2:]


class FakeRPCClient:
    def __init__(self) -> None:
        self.calldata = encode_upgrade_to_and_call(NEW_IMPL, bytes.fromhex(NESTED_SELECTOR[2:]) + b"\x00" * 32)

    def call(self, method: str, params: list[object]) -> object:
        if method == "eth_blockNumber":
            return "0x20"
        if method == "eth_getLogs":
            return [{
                "address": PROXY,
                "blockNumber": "0x10",
                "transactionIndex": "0x1",
                "logIndex": "0x0",
                "transactionHash": TX_HASH,
                "topics": [UPGRADED_TOPIC, storage_word(NEW_IMPL)],
                "data": "0x",
            }]
        if method == "eth_getTransactionByHash":
            return {
                "hash": TX_HASH,
                "blockNumber": "0x10",
                "blockHash": "0x" + "66" * 32,
                "from": ADMIN,
                "to": PROXY,
                "input": self.calldata,
                "value": "0x0",
            }
        if method == "eth_getTransactionReceipt":
            return {
                "transactionHash": TX_HASH,
                "blockNumber": "0x10",
                "status": "0x1",
                "gasUsed": "0x100",
                "logs": [],
            }
        if method == "eth_chainId":
            return hex(11155111)
        if method == "eth_getBlockByNumber":
            return {"number": "0x10", "timestamp": "0x100"}
        if method == "debug_traceTransaction":
            return {
                "type": "CALL",
                "from": ADMIN,
                "to": PROXY,
                "input": self.calldata,
                "calls": [{
                    "type": "DELEGATECALL",
                    "from": PROXY,
                    "to": NEW_IMPL,
                    "input": NESTED_SELECTOR + "00" * 32,
                }],
            }
        if method == "eth_getStorageAt":
            _, slot, block_tag = params
            self.assert_slot(slot)
            return storage_word(OLD_IMPL if block_tag == "0xf" else NEW_IMPL)
        raise AssertionError(f"unexpected RPC method: {method}")

    @staticmethod
    def assert_slot(slot: object) -> None:
        if slot != IMPLEMENTATION_SLOT:
            raise AssertionError(f"unexpected storage slot: {slot}")


class ProxyUpgradeTests(unittest.TestCase):
    def test_decode_upgrade_to_and_call(self) -> None:
        calldata = encode_upgrade_to_and_call(NEW_IMPL, bytes.fromhex("deadbeef") + b"\x00" * 32)
        decoded = decode_upgrade_call(calldata, expected_proxy=PROXY)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["implementation"], NEW_IMPL)
        self.assertEqual(decoded["implementation_selector"], NESTED_SELECTOR)

    def test_proxy_upgrade_playbook_builds_flag_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CaseStore.create(
                Path(temp_dir) / "bridge-02",
                CaseConfig(name="bridge-02", chain_id=11155111),
            )
            result = run_proxy_upgrade_playbook(
                FakeRPCClient(),
                store,
                store.load_config(),
                PROXY,
                from_block=0,
                to_block=32,
            )
            self.assertTrue(result["passed"])
            self.assertEqual(result["implementation_selector"], NESTED_SELECTOR)
            self.assertEqual(result["flag"], f"SCAN2024{{{NESTED_SELECTOR}}}")
            self.assertTrue(Path(result["evidence_path"]).exists())


if __name__ == "__main__":
    unittest.main()
