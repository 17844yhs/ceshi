"""LangGraph 检测流水线 — extract → rule_check → llm_judge → reconcile

用状态机而非函数链的原因：
  1. 每个环节的输入输出在 State 中显式可见，天然支持审计与断点调试；
  2. 后续扩展（如裁判低置信 → 带上下文重试 1 次的循环边）只需加一条
     conditional edge，与 legalMind 项目 Self-Reflection 门控同构。
"""
import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.core.llm_judge import JudgeVerdict
from app.core.rules import RuleHit, run_rules
from app.core.taxonomy import REVIEW_THRESHOLD, TYPE_LABELS, max_severity

logger = logging.getLogger("app.graph")


class DetectState(TypedDict):
    item: dict                 # 输入三元组 {id?, user_question, system_reply, knowledge_base}
    rule_hits: list[RuleHit]   # 规则层命中
    verdict: JudgeVerdict      # 裁判层判定
    result: dict               # 仲裁后的最终结果


# ─────────────────────────── 节点 ───────────────────────────


def extract_node(state: DetectState) -> dict[str, Any]:
    """特征抽取（当前由规则/裁判内部按需抽取；节点保留用于审计埋点与后续复用）"""
    logger.debug("extract item=%s", state["item"].get("id", "?"))
    return {}


def rule_check_node(state: DetectState) -> dict[str, Any]:
    return {"rule_hits": run_rules(state["item"])}


def llm_judge_node(state: DetectState) -> dict[str, Any]:
    from app.core.detector import get_judge  # 延迟导入避免循环依赖

    return {"verdict": get_judge().judge(state["item"])}


def reconcile_node(state: DetectState) -> dict[str, Any]:
    """仲裁层：类型取并集、严重度取最高（宁可多报不漏报）、置信度加权融合。"""
    rule_hits: list[RuleHit] = state["rule_hits"]
    verdict: JudgeVerdict = state["verdict"]
    item = state["item"]

    hits = list(rule_hits) + list(verdict.hits)
    fallback = verdict.fallback

    if not hits:
        result = {
            "id": item.get("id"),
            "label": "none",
            "types": [],
            "type_labels": [],
            "primary_type": None,
            "severity": "none",
            "partial": False,
            "confidence": 0.8,
            "needs_review": False,
            "evidence": [],
            "rule_hits": [h.rule for h in rule_hits],
            "judge_fallback": fallback,
            "judge_raw": verdict.raw,
        }
        return {"result": result}

    # 仲裁置信度：同一类型被规则层与裁判层同时命中 → 独立证据源互证，置信度上调
    rule_types = {h.htype for h in rule_hits}
    judge_types = {h.htype for h in verdict.hits}
    base_conf = max(h.confidence for h in hits)
    cross_confirmed = bool(rule_types & judge_types)
    confidence = min(base_conf + (0.06 if cross_confirmed else 0.0), 0.98)
    # 显式复核标记（如 C5 模糊带）直接采纳
    needs_review = any(h.meta.get("needs_review") for h in hits) or confidence < REVIEW_THRESHOLD

    # 类型并集按严重度降序排列；partial → 主类型严重度封顶 MEDIUM
    partial = any(h.partial for h in hits)
    types = sorted(
        {h.htype for h in hits},
        key=lambda t: -max(h.confidence for h in hits if h.htype == t),
    )
    severity = "low"
    for h in hits:
        severity = max_severity(severity, h.severity)
    if partial and severity == "high":
        severity = "medium"

    result = {
        "id": item.get("id"),
        "label": "hallucination",
        "types": types,
        "type_labels": [TYPE_LABELS.get(t, t) for t in types],
        "primary_type": types[0],
        "severity": severity,
        "partial": partial,
        "confidence": round(confidence, 2),
        "needs_review": needs_review,
        "evidence": list(dict.fromkeys(h.evidence for h in hits)),
        "rule_hits": [h.rule for h in rule_hits],
        "judge_fallback": fallback,
        "judge_raw": verdict.raw,
    }
    return {"result": result}


# ─────────────────────────── 图构建 ───────────────────────────


def build_detection_graph():
    workflow = StateGraph(DetectState)
    workflow.add_node("extract", extract_node)
    workflow.add_node("rule_check", rule_check_node)
    workflow.add_node("llm_judge", llm_judge_node)
    workflow.add_node("reconcile", reconcile_node)

    workflow.set_entry_point("extract")
    workflow.add_edge("extract", "rule_check")
    workflow.add_edge("rule_check", "llm_judge")
    workflow.add_edge("llm_judge", "reconcile")
    workflow.add_edge("reconcile", END)
    return workflow.compile()
