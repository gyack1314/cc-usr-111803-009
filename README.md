# 猪价研究观点与现货证据引用采集

现有项目保存机构报告与现货引用的冻结来源响应。transport 核对请求和原文字节，domain 提取来源声明的资料身份，ledger 原子保存版本，view 展示已收资料及待核状态。collection 将来源目录、待收范围与接收进度持久保存，archive 保留已发布视图所引用的资料状态。

视图把三类资料按业务事实分开：`spot_reference` 是仅覆盖其观察周的现货事实，`market_report` 是带预测周的未来预测（观察周实绩取得前不标已证实），`report_amendment` 是按 `replaces_revision` 核对的后续修订。修订说明先到而新版报告未取得时，旧报告保持 `revision_pending`、不充当现行观点且禁止发布已核实视图；新版到达后旧版转 `superseded`，现货依据仍只支持原观察周。来源缺失时 `pending_relations` 给出具体待核关系，已收原文可凭 sha256 取回。合成样例不访问外部站点。来源字段见 docs/source-contract.md。

在项目根目录运行：

    python -m unittest discover -s tests -v
    python -m compileall -q capture_service tests
    python -m capture_service.cli inspect data/normal.json
    python -m capture_service.cli receipt data/normal.json <body_sha256>

容器运行：docker build -t pork-collection-009 .；docker run --rm pork-collection-009。
