# Changelog

本项目的所有显著变更都记录在此文件中。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.0] - 2026-09-29

### Added
- 幻觉分类体系：C1 事实矛盾 / C2 无据虚构 / C3 能力越界 / C4 安全误导 / C5 信息遗漏，三级严重度（CRITICAL/HIGH/MEDIUM/LOW 映射见 taxonomy）
- 三层检测流水线（规则层 → LLM 裁判层 → 仲裁层），LangGraph 状态机编排
- Mock / Real 双模式裁判（mock 零外部依赖；real 走 OpenAI 兼容 API 结构化输出）
- Flask API：`POST /api/detect`、`POST /api/batch`、`GET /api/eval`、`GET /api/health`
- 评测服务：混淆矩阵、宏平均 P/R/F1、漏检/误报清单与误判归因
- CLI：`uv run python scripts/run_eval.py` 一键跑批
- Vue3 + Vite + Pinia 看板：检测看板 /detect、评测报告 /report
- pytest 单元与端到端测试（20 条数据集 mock 全流程）
- GitHub Actions CI（ruff + pytest）
