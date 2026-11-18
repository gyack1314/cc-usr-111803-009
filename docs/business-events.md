# 来源变化

机构发新版观点时，旧观点引用的现货资料仍按当时取得的版本保留；现货事实只支持其自身观察周，不会因为报告改指新预测周而被重新标记。

event-pending.json 表示来源目录已发现资料但正文尚未取得，event-complete.json 表示补取的原文字节（修订说明 report_amendment）已进入接收链。

修订生命周期在视图中的表现：

1. 修订说明先到、新版报告未取得：修订 `pending`，被替换报告 `revision_pending`，`current_prediction` 为空，`pending_relations` 列出 `amendment_awaits_report`，必需来源不可核实，`release_verified` 拒绝发布。
2. 新版报告到达且预测期与修订一致：修订 `fulfilled`，旧报告 `superseded`，新报告成为 `current`；旧版引用的现货依据随历史版本保留。
3. 新版报告预测期与修订不符：修订 `inconsistent`，整体保持待核、不可发布。
4. 被替换的报告原文缺失：修订 `unverifiable`，同时列出 `report_missing`。

任何阶段已收原文都不隐藏，读者可凭收据 sha256 取回机构原话；待核关系显示具体缺什么，而不是宣称已证实。
