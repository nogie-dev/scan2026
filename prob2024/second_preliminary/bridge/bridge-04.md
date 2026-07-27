# SCAN 2024 Second Preliminary — Bridge 4

- **예선:** Second preliminary round
- **카테고리:** Bridge
- **문제 번호:** 4

---

## Task

In question 3, the signers who signed the withdrawal data are not registered operator signers of the bridge. Find the hash value of the first transaction that performed a withdrawal using signatures from addresses other than the operators registered in the bridge.

## Flag Format

`SCAN2024{TransactionHash}`

- Case-insensitive

---

## 풀이 메모

- 분석 대상: Sepolia MockBridge proxy `0x39954De76b4F64E7eA5D7f906fCD943dcEF6f9Bb`
- 체인/기준 블록: chain ID `11155111` (`0xaa36a7`), Q3 기준 블록 `6,898,631` (`0x6943c7`)
- 사용 도구: Dune `sepolia.logs`/`sepolia.traces`, Sepolia JSON-RPC `https://sepolia.drpc.org`
- 조사 범위: `Withdrew` topic
  `0x21e88e956aa3e086f6388e899965cef814688f99ad8bb29b08d396571016372d`를 기준으로
  기준 블록까지 조회하고, 동일 transaction의 여러 event는 하나로 dedupe했다. 총 261건이다.
- 핵심 관찰:
  - `submitWithdrawal` selector는 `0x4d0d6673`이다.
  - 각 `submitWithdrawal` trace 반환값의 마지막 20바이트를 `ecrecover` signer로 해석했다.
  - signer별 첫 등장 순서는 다음과 같다.

    | signer | withdrawal transaction 수 | 첫 block / tx index | 등록 여부 |
    | --- | ---: | --- | --- |
    | `0x7f84691a6d962ec493fd4a2b36156d8bdec7abac` | 29 | 6898366 / 1 | 등록 |
    | `0x0725edcf85a4a4eb9820ce1cae2c3e1d380c6555` | 230 | 6898396 / 1 | 등록 |
    | `0xa0548748cc8a7fb05245bd6be9b73372e31e039a` | 1 | 6898451 / 4 | 비등록 |
    | `0x1a25d7003bc53df359ef68f5ca86b2a23926738c` | 1 | 6898631 / 8 | 비등록 |

  - 첫 비등록 signer transaction은 block `6898451`, tx index `4`의
    `0x83e3bc8d5c9c53a295cdc2203817801fe5424cde7034661c9fd0a61e221a6703`이다.
  - RPC receipt의 status는 `0x1`이고, `debug_traceTransaction`의 precompile
    `0x0000000000000000000000000000000000000001` 반환값도
    `0xa0548748cc8a7fb05245bd6be9b73372e31e039a`로 일치한다.
- 재현 자료:
  - [Dune signer audit](https://dune.com/queries/8124045)
  - [Dune first unauthorized transaction](https://dune.com/queries/8124032)
  - RPC transaction/receipt/trace 조회:

    ```sh
    TX=0x83e3bc8d5c9c53a295cdc2203817801fe5424cde7034661c9fd0a61e221a6703
    RPC=https://sepolia.drpc.org
    curl -s -H 'content-type: application/json' \
      --data '{"jsonrpc":"2.0","id":1,"method":"eth_getTransactionByHash","params":["'"$TX"'"]}' "$RPC"
    curl -s -H 'content-type: application/json' \
      --data '{"jsonrpc":"2.0","id":2,"method":"eth_getTransactionReceipt","params":["'"$TX"'"]}' "$RPC"
    curl -s -H 'content-type: application/json' \
      --data '{"jsonrpc":"2.0","id":3,"method":"debug_traceTransaction","params":["'"$TX"'",{"tracer":"callTracer"}]}' "$RPC"
    ```

- 정답: `SCAN2024{0x83e3bc8d5c9c53a295cdc2203817801fe5424cde7034661c9fd0a61e221a6703}`
