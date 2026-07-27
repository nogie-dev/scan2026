# SCAN 2024 Second Preliminary — Bridge 1

- **예선:** Second preliminary round
- **카테고리:** Bridge
- **문제 번호:** 1

---

## Intro

When a user performs a withdrawal, [MockBridge](https://sepolia.etherscan.io/address/0x39954De76b4F64E7eA5D7f906fCD943dcEF6f9Bb) collects multiple signatures from registered operators and mints new tokens. However, due to an incorrect Implementation contract upgrade by the developer, a vulnerability occurred in the bridge, leading to the theft of the bridge's assets. Analyze the process of this incident.

## Task

MockBridge approves a withdrawal transaction when the total weight of the submitted signatures' signers exceeds a specific threshold. Currently, from the bridgeManager contract of MockBridge, find all operator addresses whose weight is greater than 0, and submit the found operator addresses sorted in ascending order (e.g., address1, address2 when address1 < address2).

## Flag Format

`SCAN2024{address1, address2, address3,...}`

- Case-insensitive

---

## 풀이 메모

- 분석 대상:
- 사용 도구:
- 핵심 관찰:
- 정답:
