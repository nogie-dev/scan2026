# scan2026 / chainctf

`chainctf`는 디지털자산 추적 CTF에서 반복되는 온체인 증거 수집과 검증을 자동화하는 읽기 전용 CLI입니다. 정답을 추측하는 대신 원시 RPC 응답을 케이스별로 보존하고, 트랜잭션 dossier와 검증 결과를 재현 가능한 형태로 만듭니다.

## MVP 범위

- 케이스 디렉터리와 체인·RPC 환경변수 관리
- 트랜잭션, receipt, block, `callTracer` 결과 수집 및 캐시
- ERC-20 `Transfer` 로그와 호출 트리 정규화
- chain ID, tx/receipt hash, block, 실행 상태 검증
- Markdown 근거 보고서 생성
- RPC URL과 API 키를 파일에 저장하지 않는 read-only 기본값

기존 `scripts/env_check.py`, `scripts/rpc_collect.py`, `route.md`는 빠른 단발 조사에 계속 사용할 수 있습니다. `chainctf`는 여러 문제를 케이스 단위로 축적하고 동일한 검증·보고 형식을 적용할 때 사용합니다.

## 설치

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

## 사용 사이클

```sh
chainctf case init bridge-04 \
  --chain-id 11155111 \
  --rpc-env SEPOLIA_RPC_URL \
  --target 0x39954de76b4f64e7ea5d7f906fcd943dcef6f9bb

export SEPOLIA_RPC_URL='https://...'

chainctf collect tx 0x<transaction-hash> \
  --case .chainctf/bridge-04 \
  --trace

chainctf inspect tx 0x<transaction-hash> --case .chainctf/bridge-04
chainctf verify tx 0x<transaction-hash> --case .chainctf/bridge-04
chainctf report tx 0x<transaction-hash> --case .chainctf/bridge-04
```

케이스 구조:

```text
.chainctf/bridge-04/
├── case.json
├── raw/
│   └── transactions/<tx-hash>.json
└── reports/<tx-hash>.md
```

## 테스트

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

상세 아키텍처와 다음 단계는 [`docs/chainctf-design.md`](docs/chainctf-design.md)를 참고합니다.
