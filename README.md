# Hondui Red Team

面向大语言模型应用的自动化红队测试框架。

## 环境要求

- CPython 3.12
- [uv](https://docs.astral.sh/uv/)

## 初始化

```powershell
uv sync
```

## 运行测试

```powershell
uv run pytest
```

## 运行 CLI

```powershell
uv run redteam --help
uv run redteam version
```

## 配置迁移

破坏性配置变更及迁移示例见 [MIGRATIONS.md](MIGRATIONS.md)。

## 目录职责

```text
src/redteam/core/          领域模型、公共接口、TaskRunner 和状态机
src/redteam/config/        YAML、CLI 配置与测试资源加载
src/redteam/attacker/      Attacker Agent、攻击策略和 ModelClient
src/redteam/target/        TargetAdapter、目标调用和会话管理
src/redteam/evaluation/    Scorer、评估结果与评估聚合
src/redteam/persistence/   SQLite、运行记录与证据持久化
src/redteam/reporting/     JSON、JSONL 和 Markdown 报告
tests/unit/                单元测试
tests/contract/            模块接口契约测试
tests/integration/         端到端集成测试
```
