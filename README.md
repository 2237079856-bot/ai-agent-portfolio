# 杜晨鑫 · AI Agent 工程与研究作品集

中国科学技术大学在读硕士，方向聚焦大模型应用、检索增强与自动化评测。

| 项目 | 解决的问题 | 可以直接查看 |
| --- | --- | --- |
| **SQL Agent** | 自然语言查 SQLite。遇到执行错误时利用数据库反馈修正一次，并验证查询结果。 | [源码、离线演示与评测](projects/sql-agent/README.md) · [逐题判分记录](projects/sql-agent/evaluation/run-summary.json) |
| **QC-RAG** | 从配方专利检索量化证据、同专利对比和跨专利支持，辅助生成可追溯回答。 | [系统架构、120 题对照与版本口径](projects/qc-rag/README.md) |
| **FormuGuard-Agent** | 将检索结果绑定到声明级证据，核查出处和适用条件，支持失败定位与受控修订。 | [流程图与缺证据案例](projects/formuguard/README.md) |

## 60 秒体验 SQL Agent

在仓库根目录运行。Python 3.10 及以后版本即可，无需 GPU、模型密钥或安装第三方包。

~~~sh
python projects/sql-agent/demo.py
~~~

| 演示场景 | 可检查的结果 |
| --- | --- |
| 首次 SQL 引用了不存在的字段 | 查询报错后触发一次修复，返回合成数据中的正确件数 |
| SQL 执行成功，月份格式错误 | 离线判分标记失败，展示执行反馈机制的边界 |
| 查询工具收到不允许的写操作 | SQLite 只读执行层拦截 |

SQL Agent 在本地 Chinook 样例上以同一批首次生成为对照，主配置在 **24 道只读查询中由 18 道正确提高到 21 道**。演示用固定模型回包复现控制流程，原始实验用本地 Qwen2.5-Coder-7B-Instruct 执行。[实验方法与局限](projects/sql-agent/README.md#评测)
