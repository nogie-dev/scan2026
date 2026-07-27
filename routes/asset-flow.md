# Asset Flow

주소 사이의 자산 이동 경로, 금액과 최종 도착지를 조사한다.

## Flow

1. 시작 주소, 자산, 방향과 블록 또는 시간 범위를 고정한다.
2. 체인에 맞는 전송 유형을 구분한다.
   - EVM: native transfer, internal call, ERC-20/721/1155 event
   - Bitcoin 계열: transaction input, output, UTXO와 change
3. 각 hop의 transaction, 상대 주소, 자산, 금액과 수수료를 수집한다.
4. swap, bridge, wrapping과 unwrap을 발견하면 전후 자산의 연속성을 확인한다.
5. 반복 수집, 합산과 정렬은 스크립트로 수행한다.
6. 문제의 요구값에 기여하지 않는 다음 hop은 추적하지 않는다.

원시 전송 기록과 계산 결과를 분리한다. 잔액 변화만으로 전송 원인을 단정하지 않고
transaction, event 또는 UTXO로 확인한다.
