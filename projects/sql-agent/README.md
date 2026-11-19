# SQL Agent · 自然语言查数

在数字媒体商店样例数据库上，把自然语言问题转成可执行的 SQLite 查询。主配置将表结构、字段语义和连接键提供给模型，由执行器限制数据操作。数据库报错时，模型最多接收一次诊断反馈并重写查询。

**我的工作**包括编写 Python 执行反馈流程和本地模型调用入口，整理 Chinook 字段口径，构建固定测试题，比较单次生成与一次修复的结果，并复查失败类型。

~~~mermaid
flowchart LR
    Q["自然语言问题"] --> C["表结构 + 字段说明"]
    C --> M["本地 Qwen 生成查询"]
    M --> E["SQLite 只读执行器"]
    E -->|结果| R["返回数据"]
    E -->|首次执行报错| F["候选 SQL 与诊断反馈"]
    F --> M
    R --> J["离线按结果行判分"]
~~~

## 运行离线演示

在本目录运行以下命令。

~~~sh
python demo.py
~~~

[演示脚本](demo.py)创建一份临时合成数据库，并通过固定模型回包调用原始评测代码的查询执行和修复循环。三个场景分别覆盖缺字段后的修复成功、执行成功但返回格式错误和写操作拦截。

## 评测

模型为 Qwen2.5-Coder-7B-Instruct Q4_K_M，通过 llama.cpp b6837 本地推理。评测用 24 道只读留出题，另用 4 道拒绝题记录拒绝情况。每个配置在同一道题上复用首次生成结果，以增加一次执行反馈修复作为干预。判分比较候选查询和标准查询的实际结果行，含排序要求的题按行序比对。标准查询用于判分。

| 给模型的上下文 | 首次正确 | 修复后正确 | 触发修复 | 修复成功 |
| --- | ---: | ---: | ---: | ---: |
| 表结构和字段说明（主配置） | 18/24 | 21/24 | 5 | 3 |
| 表结构（对照配置） | 20/24 | 21/24 | 3 | 1 |

主配置复跑得到相同计数。首次执行成功但结果不符合业务要求时，当前程序不会自动改写，Q15 是这一类错误。结果反映该固定题集上的离线实验。归档的[逐题判分摘要](evaluation/run-summary.json)保留各次尝试的执行状态和判分，不含数据库返回的明细行。

## 用本地模型复跑

准备 [Chinook 原始项目的 SQLite 样例库](https://github.com/lerocha/chinook-database/releases)，以及可访问 OpenAI 兼容 Chat Completions 路径的本地服务。Chinook 协议见[上游许可](https://github.com/lerocha/chinook-database/blob/master/LICENSE.md)。本仓库提供评测代码与题目，样例库与权重由使用者自行准备。精确复现需对照摘要中记录的数据库哈希，且数据库表名和字段需与本项目题集匹配。

~~~sh
python run_eval_7b_v3.py --db path/to/chinook.db --cases evaluation/holdout.json --out runs/main.json
python run_eval_7b_v2.py --db path/to/chinook.db --cases evaluation/holdout.json --out runs/schema-only.json
~~~

默认端点为本机的 17941 端口。可用参数 --endpoint 指定已有本地服务。脚本记录哈希、各题执行结果和计数。演示阶段建议使用样例数据库。应用到业务库时，字段授权、敏感结果处理以及并发资源限制需要另行设计。
