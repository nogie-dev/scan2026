# chainctf 설계

## 목표

`chainctf`는 디지털자산 추적 문제를 자동으로 맞히는 도구가 아니라, 문제에서 요구하는 값을 찾는 과정 중 반복되는 작업을 표준화하는 도구다.

```text
Task / clue
  → CaseConfig(chain, target, reference block, expected output)
  → Collector(RPC / explorer / bridge / UTXO)
  → immutable raw cache
  → Normalizer(transaction / call / transfer / state / signature)
  → Playbook(candidate extraction and ranking)
  → Verifier(block-tagged RPC checks)
  → Reporter(flag material + evidence + reproduction commands)
```

MVP는 EVM transaction 수집, ERC-20 transfer와 call trace 정규화, deterministic verification, Markdown report 생성까지 구현한다.

## 설계 원칙

### Evidence first

원시 응답은 해석 결과와 분리해 저장한다. 정규화 코드가 바뀌어도 RPC를 다시 호출하지 않고 dossier를 재생성할 수 있어야 한다.

### Historical correctness

`current` 상태와 사건 발생 당시 상태를 구분한다. 향후 storage·operator·proxy playbook은 transaction block을 `eth_call`과 `eth_getStorageAt`의 block tag로 사용한다.

### Read-only by default

트랜잭션 전송, 서명, approve와 상태 변경 RPC는 구현 범위에서 제외한다. RPC endpoint는 `case.json`에 저장하지 않고 환경변수 이름만 기록한다.

### Provider portability

표준 JSON-RPC를 우선하며 trace가 없는 노드에서는 수집 자체는 성공하고 `trace_error`를 증거에 기록한다. provider 고유 기능은 adapter로 격리한다.

### Explainable candidates

향후 playbook 결과는 주소나 해시만 반환하지 않고, 어떤 조건을 통과했는지와 탈락 후보가 무엇인지 기록한다.

## 현재 구조

```text
src/chainctf/
├── cli.py       argparse 기반 명령 라우팅
├── core.py      case, RPC, collection, normalization, verification, report
├── __init__.py
└── __main__.py
```

기능 확장 시 아래 경계로 분리한다.

```text
chainctf/
├── cases/
├── collectors/
│   ├── evm_rpc.py
│   ├── explorer.py
│   ├── layerzero.py
│   └── bitcoin.py
├── normalizers/
│   ├── evm.py
│   └── utxo.py
├── playbooks/
│   ├── proxy_upgrade.py
│   ├── signer_recovery.py
│   ├── account_abstraction.py
│   ├── asset_flow.py
│   └── utxo_relay.py
├── verification/
└── reporting/
```

## 데이터 계약

### CaseConfig

```json
{
  "name": "bridge-04",
  "chain_id": 11155111,
  "rpc_env": "SEPOLIA_RPC_URL",
  "targets": ["0x..."],
  "reference_block": null
}
```

### Raw transaction evidence

```json
{
  "schema_version": 1,
  "collected_at": "...",
  "chain_id": 11155111,
  "transaction": {},
  "receipt": {},
  "block": {},
  "trace": {},
  "trace_error": null
}
```

원시 evidence 파일은 tx hash별 snapshot으로 저장한다. 동일 tx를 재수집하면 명시적으로 덮어쓰며 수집 시각을 남긴다.

### Transaction dossier

- transaction summary: hash, block, timestamp, from, to, status, selector
- ERC-20 transfer: token, from, to, raw amount, log index
- call tree: path, depth, type, caller, callee, selector, value, gas, error
- trace availability

## 명령 책임

- `case init`: 분석 범위와 RPC 환경변수 이름을 고정한다.
- `collect tx`: 노드의 원시 응답만 수집한다.
- `inspect tx`: 캐시에서 dossier를 생성하며 네트워크에 접근하지 않는다.
- `verify tx`: chain ID, hash, block, status, schema를 검사한다.
- `report tx`: 정규화 결과와 검증 체크를 Markdown으로 고정한다.

## 개발 로드맵

### Phase 1 — Transaction dossier

현재 구현 범위다.

- case lifecycle
- tx·receipt·block·trace cache
- ERC-20 transfers
- call tree
- deterministic checks
- Markdown report

### Phase 2 — CTF playbooks

1. `proxy-upgrade`: EIP-1967 implementation, `Upgraded`, upgrade-and-call selector
2. `recover-signers`: calldata·digest adapter, `ecrecover`, operator set 비교
3. `asset-flow`: ERC-20/native transfer graph, common receiver와 hop 추적
4. `erc4337`: EntryPoint `handleOps`와 account execution 펼치기
5. `layerzero`: source tx, GUID, destination tx 연결

### Phase 3 — Bulk query plane

- `eth_getLogs` adaptive block chunking
- Parquet/DuckDB optional dependency
- Dune query adapter
- address/token/time aggregation
- cache manifest와 provenance

### Phase 4 — UTXO

- BTC transaction/input/output normalizer
- OP_RETURN extraction
- UTXO provenance와 relay grouping
- deterministic ordering과 flag hashing

## 완료 기준

새 playbook은 다음 조건을 만족해야 한다.

- 체인과 기준 블록이 명시된다.
- 원시 증거와 해석 결과가 분리된다.
- 후보 선정 이유가 기계적으로 재현된다.
- 외부 라벨만으로 소유자를 확정하지 않는다.
- fixture 기반 unit test가 있다.
- report에 tx/address/block과 검증 결과가 포함된다.
