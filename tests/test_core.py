from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chainctf.core import TRANSFER_TOPIC, CaseConfig, CaseStore, build_dossier, verify_evidence

TX_HASH = "0x" + "ab" * 32
FROM = "0x" + "11" * 20
TO = "0x" + "22" * 20
TOKEN = "0x" + "33" * 20
RECEIVER = "0x" + "44" * 20


def address_topic(address: str) -> str:
    return "0x" + "0" * 24 + address[2:]


def sample_evidence() -> dict:
    return {
        "schema_version": 1,
        "chain_id": 11155111,
        "transaction": {
            "hash": TX_HASH,
            "blockNumber": "0x10",
            "from": FROM,
            "to": TO,
            "input": "0x12345678" + "00" * 32,
            "value": "0x0",
        },
        "receipt": {
            "transactionHash": TX_HASH,
            "blockNumber": "0x10",
            "status": "0x1",
            "gasUsed": "0x5208",
            "contractAddress": None,
            "logs": [{
                "address": TOKEN,
                "topics": [TRANSFER_TOPIC, address_topic(FROM), address_topic(RECEIVER)],
                "data": "0x64",
                "logIndex": "0x0",
            }],
        },
        "block": {"timestamp": "0x65"},
        "trace": {
            "type": "CALL",
            "from": FROM,
            "to": TO,
            "input": "0x12345678",
            "value": "0x0",
            "gasUsed": "0x100",
            "calls": [{
                "type": "CALL",
                "from": TO,
                "to": TOKEN,
                "input": "0xa9059cbb",
                "value": "0x0",
                "gasUsed": "0x50",
            }],
        },
        "trace_error": None,
    }


class CoreTests(unittest.TestCase):
    def test_case_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "case"
            store = CaseStore.create(root, CaseConfig(name="demo", chain_id=11155111))
            self.assertEqual(store.load_config().name, "demo")
            path = store.save_evidence(TX_HASH, sample_evidence())
            self.assertTrue(path.exists())
            self.assertEqual(store.load_evidence(TX_HASH)["chain_id"], 11155111)

    def test_dossier_decodes_transfer_and_calls(self) -> None:
        dossier = build_dossier(sample_evidence())
        self.assertEqual(dossier["selector"], "0x12345678")
        self.assertEqual(dossier["token_transfers"][0]["amount_raw"], 100)
        self.assertEqual(dossier["token_transfers"][0]["to"], RECEIVER)
        self.assertEqual(len(dossier["calls"]), 2)
        self.assertEqual(dossier["calls"][1]["selector"], "0xa9059cbb")

    def test_verification_detects_chain_mismatch(self) -> None:
        checks = verify_evidence(CaseConfig(name="demo", chain_id=1), sample_evidence(), TX_HASH)
        status = {item["name"]: item["passed"] for item in checks}
        self.assertFalse(status["chain_id"])
        self.assertTrue(status["transaction_hash"])
        self.assertTrue(status["execution_status"])


if __name__ == "__main__":
    unittest.main()
