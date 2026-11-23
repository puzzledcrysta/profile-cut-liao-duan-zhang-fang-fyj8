# 料段账房业务与测试登记

- 规模：中型
- 使用者：门窗加工车间备料员
- 核心规则：按订单长料优先，从最紧合的可用余料分配，计入锯缝并区分可复用料尾和报废。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 备料凭证 | 检查编码、字段宽度和来源行 | `POST /api/intake` | `app/modules/intake/service.py` | `tests/test_intake.py` |
| M2 型材规格 | 归一修订、业务键和偏移时间 | `POST /api/contract` | `app/modules/contract/service.py` | `tests/test_contract.py` |
| M3 异常计划 | 定位重复、被替代与矛盾来源 | `POST /api/quality` | `app/modules/quality/versions.py` | `tests/test_quality.py` |
| M4 型材排料 | 按规则复算并追溯证据 | `POST /api/domain` | `app/modules/domain/rule.py` | `tests/test_domain.py` |
| M5 领料核对 | 核对独立清单和各类差异 | `POST /api/reconcile` | `app/modules/reconcile/service.py` | `tests/test_reconcile.py` |
| M6 锯切批次 | 打开历史批次并对原文件复跑 | `POST /api/runs` | `app/modules/runs/service.py` | `tests/test_runs.py` |
| M7 班组复核 | 登记复核结论并下载证据 | `POST /api/review/{run_id}` | `app/modules/review/decisions.py` | `tests/test_review.py` |
| M8 合单交班 | 合单回单对账、逐单凭据补录与分级签认 | `POST /api/handover/{run_id}/receipts` | `app/modules/handover/service.py` | `tests/test_handover.py` |

## 陷阱登记

| TRAP | 现象 | 样例 | 处理位置 | 测试 |
|---|---|---|---|---|
| TRAP-01 | GB18030 来源文件 | legacy.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_gb18030` |
| TRAP-02 | BOM 前缀 | shift.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_bom` |
| TRAP-03 | 备注含引号内换行 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_multiline` |
| TRAP-04 | 分段重复表头 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_repeated` |
| TRAP-05 | 列数不足 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_width` |
| TRAP-07 | 缺测哨兵 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_missing` |
| TRAP-08 | 前导零的单号 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_leading_zero` |
| TRAP-11 | 偏移时刻 UTC 归一 | shift.csv | `app/modules/domain/values.py` | `tests/test_contract.py::test_offsets` |
| TRAP-14 | 同版业务字段冲突 | shift.csv | `app/modules/quality/versions.py` | `tests/test_quality.py::test_conflicting` |
| TRAP-16 | 末行引号截断 | truncated.csv | `app/modules/intake/reader.py` | `tests/test_intake.py::test_truncated_rejected` |
| TRAP-17 | 旧版列名映射 | legacy.csv | `app/modules/contract/schema.py` | `tests/test_contract.py::test_legacy_aliased` |
| TRAP-18 | 空文件、空白文件与仅表头 | 测试构造 | `app/modules/intake/service.py` | `tests/test_intake.py::test_empty_states` |
| TRAP-26 | 陈旧复核版本拒绝 | 测试构造 | `app/modules/review/decisions.py` | `tests/test_review.py::test_stale` |
| TRAP-27 | 合单总额相符掩盖各单一多一少 | receipts.csv | `app/modules/handover/adjudication.py` | `tests/test_handover.py::test_total_match_can_hide_one_over_one_under` |
| TRAP-28 | 同一份补录重试新增确认记录 | 测试构造 | `app/modules/handover/service.py` | `tests/test_handover.py::test_retrying_same_evidence_adds_no_record` |
| TRAP-29 | 补录凭据与原回单范围或合计不符 | 测试构造 | `app/modules/handover/service.py` | `tests/test_handover.py::test_evidence_must_match_receipt_scope_and_total` |
| TRAP-105 | kerf blocks | cases.csv | `app/modules/domain/rule.py` | `tests/test_domain.py::test_kerf_blocks` |
| TRAP-19 | best fit | cases.csv | `app/modules/domain/rule.py` | `tests/test_domain.py::test_best_fit` |

## 对账

输入 = 计入 + 隔离 + 重传及版本替换 + 空白记录 + 重复表头。按业务键全外连接，缺失一侧与数值为零分别登记。逐笔差值与总差一致。

## 合单交班

仓库把多张锯切计划并开一张领料回单时，先做回单层级判定：仅核对合单总额，逐单一律标记 `PENDING_EVIDENCE`，班组只能在总额相符时签认回单总额结论，且须注明待补录范围；总额不符 (`TOTAL_DELTA`) 禁止签认。

仓库补齐逐单凭据后重判各单差异。凭据的业务键范围必须与原回单完全一致 (`EVIDENCE_SCOPE`)，合计必须等于原回单金额 (`EVIDENCE_TOTAL`)，否则整份拒绝且不留判定记录。重判结果为 `EVIDENCE_MATCH` 或 `EVIDENCE_DELTA`；后者即便总额相符也禁止逐单签认。每次判定按序号留痕，原交班结论保留在时间线中可查。

回单登记与凭据补录均按内容幂等：同一回单同内容重试、同一字节补录重试都不新增记录；同回单号换内容登记报 `RECEIPT_CONFLICT`。
