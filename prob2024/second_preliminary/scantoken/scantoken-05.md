# SCAN 2024 Second Preliminary — ScanToken 5

- **예선:** Second preliminary round
- **카테고리:** ScanToken
- **문제 번호:** 5

---

## Task

For anti-computer forensics purposes, the attacker sent laundering transactions from a virtual machine and immediately discarded the private keys of all addresses except for the final destination address. However, the attacker made a mistake by performing a specific step in the wrong order (earlier than it should have been), causing them to acquire less ScanUSDC than they could.

Identify the transaction that was prematurely sent by mistake, and the function selector in it. (Assume that the transactions sent by the attacker do not contain incorrect calldata, and the only thing wrong is the ordering.)

## Flag Format

`SCAN2024{TransactionHash_FunctionSelector}`

- Case-insensitive

---

## 풀이 메모

- 분석 대상:
- 사용 도구:
- 핵심 관찰:
- 정답:
