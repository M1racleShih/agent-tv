# AgentTV

AgentTV 计划在 Ubuntu 本机网页中按 herdr workspace 查看 agent 会话进展，并提供可独立使用的 Record，记录 idea、TODO 和 prompt。发送采用手动复制粘贴。

目前已有需求、架构、开发计划和仓库检查程序。**产品源码与运行入口尚未创建，14 个关键产品场景仍待实现。**

## 从这里接手

- [AGENTS.md](AGENTS.md)：开发边界、工作方式和完成要求。
- [需求与 GUI 方向](docs/discovery.html)：产品目标和界面参考。
- [接入与数据设计](docs/implementation.html)：数据、状态和模块职责。
- [开发 Harness](docs/harness.html)：命令含义、检查范围和报告位置。
- [仓库启动建设](docs/plans/repository-bootstrap.html)：本次建设的决定与验收记录。
- [首轮产品计划](docs/plans/first-delivery.html)：接下来要实现的产品步骤，当前待开始。

详细设计与进度以链接的 HTML 为准。HTML 可在浏览器打开阅读。

## 检查当前仓库

在项目根目录使用 Python 3.11 或更高版本；仓库检查只依赖 Python 标准库。

```sh
python3 scripts/harness.py doctor
python3 scripts/harness.py check
python3 scripts/harness.py cases
```

`doctor` 检查本机工具和 dskills，不安装依赖。`check` 检查文档、场景登记和 harness 自身，并运行已经存在的产品工程检查。每次检查打印 `.harness/runs/` 中的 JSON 报告路径。

当前 `check` 可以通过，缺失的 Rust 和网页工程显示 `NOT_APPLICABLE`；这只证明仓库检查通过。`cases` 的 `planned` 表示测试待实现，`registered` 也需要实际运行才能取得结果。

```sh
python3 scripts/harness.py check --scope product
```

严格产品检查要求完整工程、锁文件、工具链文件和关键场景的自动命令，**当前应返回非零退出码**。未来该检查通过表示自动验证通过；真实来源接入与 GUI 实际使用仍需分别记录。

局部文档修改可运行 `check --scope docs`；只验证仓库工具可运行 `check --scope harness`。所有检查继续使用同一个脚本入口。

## 下一步

按首轮产品计划建立合成接入样例和可执行重放，再逐步提供独立 Record 与 Preview。实现时接入真实检查命令，并更新相关场景；本轮仓库建设不提前创建这些工程。

本项目使用本地 Git 的 `main` 分支保存版本，初始提交包含现有设计与仓库启动建设。技能、检查报告和构建产物由 `.gitignore` 排除；远程仓库、CI 和发布尚未配置。
