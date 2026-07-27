# SCAN 2024 First Preliminary — Tracking Investigation 3

- **예선:** First preliminary round
- **카테고리:** Tracking - Investigation
- **문제 번호:** 3

---

## Task

Identify the top 3 wallets (based on amount of received BTC from victims) receiving relayed victim transactions, which we will call Level 2 wallets. Identify how each victim transaction is relayed to the top 3 Level 2 wallets.

## Required Information

### `<victim_tx_group>`

Group of victim transaction hashes sent to Level 1 wallet, that are spend together in a single transaction hash to top 3 Level 2 wallets in the ascending order of Block Number of victim transaction hashes.

- If the Block Number is same, then in the ascending order of index in the Block.
- Each victim transaction hash is to be separated using `:` character.
- Do not include non-victim transactions.

### `<relay_tx>`

Transaction Hash spending the victim transaction group to top 3 Level 2 wallets.

### `<utxo_set>`

`victim_tx_group>relay_tx`

The `victim_tx_group` and `relay_tx` are separated by `>` character.

### Example

If 3 victim transaction hashes `1`, `2` and `3` (`victim_tx_group` = `1:2:3`) are relayed to transaction hash `4`, then:

```text
1:2:3>4
```

## Flag Format

`scanctf2024{sha256(UTXOs in the ascending order of Block Number of relay_tx separated by ",")}`

---

## 풀이 메모

- 분석 대상:
- 사용 도구:
- 핵심 관찰:
- 정답:
