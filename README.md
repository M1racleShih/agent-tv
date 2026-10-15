# AgentTV

AgentTV 计划在 Ubuntu 本机网页中按 herdr workspace 查看 agent 会话进展，并提供可独立使用的 Record，记录 idea、TODO 和 prompt。发送采用手动复制粘贴。

**当前已有设计和仓库检查程序，产品源码与运行入口尚未创建。14 个关键产品场景均待实现。**

## 开始开发

- [AGENTS.md](AGENTS.md)：开发边界与验证要求。
- [需求与 GUI 方向](docs/discovery.html)：产品目标和界面参考。
- [接入与数据设计](docs/implementation.html)：数据、状态和模块职责。
- [首轮产品计划](docs/plans/first-delivery.html)：当前进度与下一步。

下一步是建立合成接入样例和可执行重放，再逐步提供独立 Record 与 Preview。按实际需要创建产品模块，不提前搭空工程。

## 检查仓库

在项目根目录使用 Python 3.11 或更高版本；检查程序只依赖标准库。

```sh
python3 scripts/harness.py doctor  # 首次进入环境时检查工具
python3 scripts/harness.py check   # 检查仓库和已存在的产品工程
```

当前普通检查可以通过，但缺失的产品工程会显示 `NOT_APPLICABLE`，不代表产品可用。交付首版前运行严格检查：

```sh
python3 scripts/harness.py check --scope product
```

该命令目前应失败。局部检查、场景登记和报告格式见 [开发 Harness](docs/harness.html#commands)。真实接入与页面使用另行验证。

## 仓库记录

本地 Git 使用 `main` 分支，远程仓库、CI 和发布尚未配置。技能、检查报告和构建产物不进入版本控制。历史验收见 [仓库启动建设](docs/plans/repository-bootstrap.html)。
