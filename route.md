# Investigation Routes

문제에서 요구하는 결과를 기준으로 route를 고른다. 관련된 문서만 읽고 나머지는
불러오지 않는다. 여러 route가 필요하면 필요한 순서대로 연결한다.

| 문제 신호 | Route |
| --- | --- |
| 컨트랙트 코드, 프록시, 상태값, 권한 | [`routes/evm-contract.md`](routes/evm-contract.md) |
| 특정 트랜잭션의 호출과 실행 결과 | [`routes/transaction-trace.md`](routes/transaction-trace.md) |
| 코인 또는 토큰의 이동 경로와 금액 | [`routes/asset-flow.md`](routes/asset-flow.md) |
| 거래소, 브리지, VASP 등 주소의 주체 | [`routes/entity-attribution.md`](routes/entity-attribution.md) |

route를 시작할 때 다음 값을 먼저 확정한다.

```text
chain / chain id:
target:
reference block or range:
expected output:
```

분류가 애매하면 가장 직접적으로 요구값을 조회할 수 있는 route부터 시작한다.
다른 영역의 근거가 실제로 필요할 때만 다음 route를 추가한다.

## Query plane selection

route를 정한 뒤에는 문제 유형과 별개로 데이터 규모와 필요한 실행 결과에 따라
Dune 또는 RPC를 선택한다.

| 상황 | 기본 조회 방식 | 이유 |
| --- | --- | --- |
| 단순 event 수집, 좁은 block range | RPC `eth_getLogs` | 요청 수가 적고 원시 응답을 바로 확인할 수 있다. |
| 수백 건 이상의 과거 logs/traces, join, 정렬, dedupe, 집계 | Dune | SQL로 후보를 일괄 축소하고 비교할 수 있다. |
| 단일 또는 소수 transaction의 input, receipt, 내부 실행 | RPC | 노드의 실제 실행 결과와 상태를 직접 확인할 수 있다. |
| 특정 block의 `eth_call`, storage, code, proxy 상태 | RPC | block-tagged state 조회가 필요하다. |
| Dune에 체인·테이블이 없거나 trace 표현이 불완전한 경우 | RPC 또는 다른 trace provider | 데이터 coverage와 실행 표현을 우선한다. |

Dune은 대량 후보 탐색과 집계에 사용하고, precompile·trace 반환값·transaction
성공 여부처럼 실행 결과가 결론을 결정하는 값은 RPC를 최종 근거로 사용한다.
Dune query에는 partition column과 기준 block/range를 반드시 포함한다.

공통 환경과 RPC 수집기는 저장소의 `scripts/`를 사용한다.

```sh
python3 scripts/env_check.py --rpc-url "$RPC_URL" --expected-chain-id 11155111
python3 scripts/rpc_collect.py \
  --rpc-url "$RPC_URL" \
  --from-block 100 --to-block 200 \
  --address 0x... --topic0 0x... \
  --collect receipt --output evidence.json
```

`env_check.py`는 Dune MCP를 설치하지 않는다. Agent runtime에서 확인한 MCP 상태를
`--dune-available true|false|unknown` 또는 `DUNE_MCP_AVAILABLE`로 전달하고,
`DUNE_MODE=auto|prefer|required|off`에 따라 fallback 여부를 판단한다.
