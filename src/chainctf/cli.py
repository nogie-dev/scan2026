"""Command-line entry point for chainctf."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .core import (
    CaseConfig,
    CaseStore,
    ChainCTFError,
    RPCClient,
    build_dossier,
    collect_transaction,
    markdown_report,
    verify_evidence,
)
from .playbooks import run_proxy_upgrade_playbook, write_proxy_upgrade_report


def emit_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chainctf",
        description="Read-only, evidence-first CLI for blockchain investigation CTFs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    case_parser = subparsers.add_parser("case", help="Create or inspect a case")
    case_sub = case_parser.add_subparsers(dest="case_command", required=True)
    case_init = case_sub.add_parser("init", help="Create a case directory")
    case_init.add_argument("name")
    case_init.add_argument("--chain-id", type=int, required=True)
    case_init.add_argument("--rpc-env", default="SCAN_RPC_URL")
    case_init.add_argument("--target", action="append", default=[])
    case_init.add_argument("--reference-block", type=int)
    case_init.add_argument("--root", default=None, help="Defaults to .chainctf/<name>")
    case_show = case_sub.add_parser("show", help="Show case configuration")
    case_show.add_argument("--case", required=True)

    collect_parser = subparsers.add_parser("collect", help="Collect immutable raw evidence")
    collect_sub = collect_parser.add_subparsers(dest="collect_command", required=True)
    collect_tx = collect_sub.add_parser("tx", help="Collect transaction, receipt, block, and optional trace")
    collect_tx.add_argument("hashes", nargs="+")
    collect_tx.add_argument("--case", required=True)
    collect_tx.add_argument("--trace", action="store_true")

    inspect_parser = subparsers.add_parser("inspect", help="Normalize cached evidence")
    inspect_sub = inspect_parser.add_subparsers(dest="inspect_command", required=True)
    inspect_tx = inspect_sub.add_parser("tx", help="Build a transaction dossier")
    inspect_tx.add_argument("tx_hash")
    inspect_tx.add_argument("--case", required=True)

    verify_parser = subparsers.add_parser("verify", help="Verify cached evidence")
    verify_sub = verify_parser.add_subparsers(dest="verify_command", required=True)
    verify_tx = verify_sub.add_parser("tx", help="Run deterministic evidence checks")
    verify_tx.add_argument("tx_hash")
    verify_tx.add_argument("--case", required=True)

    report_parser = subparsers.add_parser("report", help="Render a reproducible report")
    report_sub = report_parser.add_subparsers(dest="report_command", required=True)
    report_tx = report_sub.add_parser("tx", help="Render a Markdown transaction report")
    report_tx.add_argument("tx_hash")
    report_tx.add_argument("--case", required=True)
    report_tx.add_argument("--output")

    playbook_parser = subparsers.add_parser("playbook", help="Run a problem-oriented investigation")
    playbook_sub = playbook_parser.add_subparsers(dest="playbook_command", required=True)
    proxy_upgrade = playbook_sub.add_parser(
        "proxy-upgrade",
        help="Find an EIP-1967 Upgraded event and extract upgrade-and-call selector evidence",
    )
    proxy_upgrade.add_argument("--case", required=True)
    proxy_upgrade.add_argument("--proxy", required=True)
    proxy_upgrade.add_argument("--from-block", type=int, default=0)
    proxy_upgrade.add_argument("--to-block", type=int)
    selection = proxy_upgrade.add_mutually_exclusive_group()
    selection.add_argument("--latest", action="store_true", help="Select the latest upgrade event (default)")
    selection.add_argument("--earliest", action="store_true", help="Select the earliest upgrade event")
    proxy_upgrade.add_argument("--output", help="Optional Markdown report path")
    return parser


def run(args: argparse.Namespace) -> int:
    if args.command == "case" and args.case_command == "init":
        root = Path(args.root or f".chainctf/{args.name}")
        store = CaseStore.create(
            root,
            CaseConfig(
                name=args.name,
                chain_id=args.chain_id,
                rpc_env=args.rpc_env,
                targets=args.target,
                reference_block=args.reference_block,
            ),
        )
        emit_json({"case": str(store.root), "config": str(store.config_path)})
        return 0

    if args.command == "case" and args.case_command == "show":
        store = CaseStore(Path(args.case))
        emit_json(store.read_json(store.config_path))
        return 0

    store = CaseStore(Path(args.case))
    config = store.load_config()

    if args.command == "collect" and args.collect_command == "tx":
        client = RPCClient.from_case(config)
        results = []
        for tx_hash in args.hashes:
            evidence = collect_transaction(client, tx_hash, trace=args.trace)
            path = store.save_evidence(tx_hash, evidence)
            results.append({"transaction_hash": tx_hash.lower(), "path": str(path), "trace": args.trace})
        emit_json({"collected": results})
        return 0

    if args.command == "playbook" and args.playbook_command == "proxy-upgrade":
        client = RPCClient.from_case(config)
        result = run_proxy_upgrade_playbook(
            client,
            store,
            config,
            args.proxy,
            from_block=args.from_block,
            to_block=args.to_block,
            latest=not args.earliest,
        )
        report_path = write_proxy_upgrade_report(store, result, args.output)
        result["report_path"] = str(report_path)
        emit_json(result)
        return 0 if result["passed"] else 2

    evidence = store.load_evidence(args.tx_hash)
    if args.command == "inspect" and args.inspect_command == "tx":
        emit_json(build_dossier(evidence))
        return 0

    checks = verify_evidence(config, evidence, args.tx_hash)
    if args.command == "verify" and args.verify_command == "tx":
        passed = all(check["passed"] for check in checks)
        emit_json({"passed": passed, "checks": checks})
        return 0 if passed else 2

    if args.command == "report" and args.report_command == "tx":
        dossier = build_dossier(evidence)
        report = markdown_report(config, dossier, checks)
        output = Path(args.output) if args.output else store.reports / f"{args.tx_hash.lower()[2:]}.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
        print(output)
        return 0

    raise ChainCTFError("unsupported command")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (ChainCTFError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
