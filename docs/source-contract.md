# 来源字段

market_report 与 spot_reference 的 report_id 是来源声明的关联线索；字段相等不证明两份原文已经完整或同版，也不能单独把观点配成“已核实”。

三类资料在视图中按业务事实分开呈现：

- `spot_reference`（现货事实）：只陈述其 `observed_week` 观察周的价格（如 2026-W46 的 8.66 元/公斤）。事实范围不随报告版次迁移，永远不能被标记为其他周（如 2026-W48）的实绩。
- `market_report`（未来预测）：每个报告版次声明自己的 `prediction_week`。预测周的现货观察取得前，预测保持“未来预测”，并在 `pending_relations` 中列出 `prediction_without_observation` 待核关系。
- `report_amendment`（后续修订）：按 `replaces_revision` 指向被替换的报告版次。修订说明先到而新版报告原文未取得时，修订为 `pending`、旧报告标记为 `revision_pending`（不是现行观点，`release_verified` 拒绝发布）；新版报告到达且预测期一致后修订转为 `fulfilled`，旧版转为 `superseded` 历史预测；预测期不一致时为 `inconsistent`，保持待核。被替换版次原文缺失时修订为 `unverifiable`。

`matched_pairs` 仅表示“报告引用了观察周更早的现货”，每条都带 `prediction_week` 与 `observed_week`，属于引用依据而非预测证实。来源缺失时视图不隐藏已收原文，而是在 `pending_relations` 给出带编号的具体待核关系（`report_missing`、`spot_reference_missing`、`amendment_awaits_report`、`prediction_without_observation`）。冻结原文可凭 `source_sha256` 通过 `ledger.raw_receipt` 或 `cli receipt` 取回核对。

来源目录中的 expected_revision 表示该链接当前要求核实的来源版次；normal.json 为 v1，revised.json 将第一份来源改指同链接 v2。旧版原文仍可用于历史视图，已发布视图（archive）冻结当时引用的报告版本与现货依据，不被后续资料改写。
