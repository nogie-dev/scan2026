# EVM Contract

컨트랙트의 실제 실행 코드, 구현체, ABI와 특정 블록의 상태를 조사한다.

## Flow

1. 대상 주소의 runtime bytecode를 확인한다.

   ```sh
   cast code "$TARGET" --block "$BLOCK" --rpc-url "$ETH_RPC_URL"
   ```

2. EIP-1967 프록시 여부와 구현체를 확인한다.

   ```sh
   cast implementation "$TARGET" --block "$BLOCK" --rpc-url "$ETH_RPC_URL"
   ```

3. 구현체가 있으면 검증된 소스와 ABI를 확인한다.

   ```sh
   cast source "$IMPLEMENTATION" \
     --chain "$CHAIN" \
     --etherscan-api-key "$ETHERSCAN_API_KEY"
   ```

4. 필요한 public getter가 있으면 ABI로 호출한다. 프록시 상태는 구현체가 아니라
   프록시 주소에서 조회한다.

   ```sh
   cast call "$TARGET" "<function-signature>" "<args>" \
     --block "$BLOCK" \
     --rpc-url "$ETH_RPC_URL"
   ```

5. getter가 없거나 관련 구현체에서 사라진 경우에만 storage를 분석한다.

   ```sh
   cast storage "$TARGET" "$SLOT" --block "$BLOCK" --rpc-url "$ETH_RPC_URL"
   cast index "<key-type>" "$KEY" "$BASE_SLOT"
   ```

6. 반환된 하위 컨트랙트 주소에는 이 route를 다시 적용한다.

## Upgrade history

구현체 변경 이력을 묻는 문제는 storage보다 `Upgraded(address)` 이벤트를 먼저 조회한다.

```sh
cast logs 'Upgraded(address)' \
  --address "$TARGET" \
  --from-block "$FROM_BLOCK" \
  --to-block "$BLOCK" \
  --rpc-url "$ETH_RPC_URL"
```

가장 최근 관련 이벤트의 transaction을 조회하고, `upgradeAndCall` 계열 외부 calldata의
`bytes` 인자를 디코딩한다. 그 bytes의 첫 4바이트가 구현체에서 실행된 내부 함수 selector다.
새 구현체 ABI 또는 trace로 selector를 교차 검증한다.

## Fallbacks

- EIP-1967 구현체가 없으면 beacon, minimal proxy, diamond와 비표준 proxy를 확인한다.
- 현재 상태와 과거 상태가 다르면 해당 블록의 구현체와 변경 이벤트를 확인한다.
- 소스가 미검증이면 bytecode selector, creation transaction과 호출 기록을 사용한다.

## Record

프록시와 구현체 주소, 기준 블록, ABI 출처, 호출 또는 slot, 원시값과 디코딩 결과를
남긴다.
