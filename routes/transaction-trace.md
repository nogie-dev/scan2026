# Transaction Trace

특정 트랜잭션의 입력, 내부 호출, 상태 변화와 이벤트를 시간순으로 조사한다.

## Flow

1. 조회 대상의 규모를 판단한다.

   - 특정 transaction 또는 소수 후보: RPC를 바로 사용한다.
   - 과거 block range에서 후보가 많거나 logs와 traces를 함께 비교: Dune으로
     후보를 먼저 줄인 뒤 RPC로 검증한다.

2. 트랜잭션과 receipt를 조회한다.

   ```sh
   cast tx "$TX_HASH" --rpc-url "$ETH_RPC_URL"
   cast receipt "$TX_HASH" --rpc-url "$ETH_RPC_URL"
   ```

3. 대상 컨트랙트의 해당 블록 구현체와 ABI를 확인한다.
4. calldata selector와 인자를 디코딩한다.
5. 내부 실행 흐름이 필요하면 trace를 조회한다.

   ```sh
   cast run "$TX_HASH" --rpc-url "$ETH_RPC_URL"
   ```

6. call, delegatecall, contract creation, value transfer, event와 revert를 순서대로 정리한다.

## Bulk reconnaissance with Dune

대량의 과거 transaction을 조사할 때는 `logs`에서 후보를 만들고, transaction hash로
`traces`를 join하여 정렬·dedupe·집계한다. 이 단계의 목적은 후보 축소와 패턴 확인이다.

- `block_number` 또는 시간 범위를 고정한다.
- partition column을 조건에 포함한다.
- 동일 transaction의 여러 event는 문제 요구에 따라 dedupe한다.
- precompile 호출이나 trace 반환값이 누락·변형될 수 있으므로 Dune 결과만으로
  최종 결론을 내리지 않는다.

후보가 정해지면 RPC에서 transaction, receipt와 debug trace를 다시 조회해 status,
실제 반환값, 내부 호출과 event를 교차 검증한다.

trace를 지원하지 않는 RPC라면 다른 archive/trace RPC로 교차 검증한다. 기록에는
transaction status, block, sender, target, decoded input, 주요 내부 호출과 이벤트를
포함한다.

## Optional Phalcon reconnaissance

호출이 복잡하거나 RPC trace가 불완전할 때 Phalcon Explorer를 보조 분석기로 사용한다.
Phalcon은 최종 근거가 아니라 핵심 호출을 찾는 탐색 단계로 사용한다.

1. transaction hash로 Phalcon Explorer를 연다.
2. Invocation Flow에서 CALL, DELEGATECALL, EVENT와 의심되는 분기를 확인한다.
3. 필요하면 Balance Changes, State Changes와 Debugger로 범위를 좁힌다.
4. Phalcon URL, 조회 시점과 확인한 node를 기록한다.
5. 최종 selector, calldata, 주소와 금액은 cast/RPC로 재검증한다.

```text
https://app.blocksec.com/phalcon/explorer/tx/eth/{transaction_hash}
```

단순 ABI 호출, selector 확인과 receipt 조회에는 Phalcon을 사용하지 않는다.
화면의 라벨이나 시각화만을 최종 근거로 사용하지 않는다.
