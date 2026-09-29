"""检测编排器 — 封装 LangGraph 流水线，提供单条/批量检测入口"""
from __future__ import annotations

import logging

from app.config import settings
from app.graph.workflow import build_detection_graph
from app.core.llm_judge import RealJudge, SimulatedJudge

logger = logging.getLogger("app.detector")

_judge_cache: dict[bool, object] = {}
_graph_cache: dict[bool, object] = {}


def get_judge():
    """按 mock 开关缓存裁判实例（图节点内调用）。"""
    if settings.HALLU_MOCK not in _judge_cache:
        _judge_cache[settings.HALLU_MOCK] = (
            SimulatedJudge() if settings.HALLU_MOCK else RealJudge()
        )
    return _judge_cache[settings.HALLU_MOCK]


def get_graph():
    if settings.HALLU_MOCK not in _graph_cache:
        _graph_cache[settings.HALLU_MOCK] = build_detection_graph()
        logger.info(
            "detection graph compiled (judge=%s)",
            "simulated" if settings.HALLU_MOCK else "llm",
        )
    return _graph_cache[settings.HALLU_MOCK]


class HallucinationDetector:
    """单条/批量幻觉检测。模式由 HALLU_MOCK 决定（mock=simulated / real=LLM）。"""

    @property
    def mode(self) -> str:
        return "mock" if settings.HALLU_MOCK else "real"

    def detect(self, item: dict) -> dict:
        state = get_graph().invoke({"item": item})
        result = dict(state["result"])
        result["mode"] = self.mode
        return result

    def detect_batch(self, items: list[dict]) -> list[dict]:
        # 20 条数据量级下顺序执行保证可复现；real 模式如需并发可在上层加信号量
        return [self.detect(item) for item in items]
