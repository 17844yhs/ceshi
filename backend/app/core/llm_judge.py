"""LLM 裁判层 — 语义矛盾/虚构判定，结构化 JSON 输出

双实现（同一接口 judge(item) -> JudgeVerdict）：
  - SimulatedJudge（mock 模式）：确定性启发式模拟裁判。覆盖语义类 case 的典型模式
    （政策天数/版本号/发货时长/材质/保修期冲突），零外部依赖，用于离线演示与回归测试。
  - RealJudge（real 模式）：OpenAI 兼容 API + 结构化 prompt；要求 evidence 必须引用
    KB 原文片段，逐句校验并输出 partial 标志；JSON 解析失败带错误上下文重试 1 次，
    仍失败则 fallback=True（仲裁层降级为仅规则结果）。

防护裁判自身幻觉：无 evidence 引用 → 判 NONE。
"""
import json
import logging
import re
from dataclasses import dataclass, field

from app.core.rules import RuleHit
from app.core.taxonomy import TYPE_LABELS

logger = logging.getLogger("app.llm_judge")

# ─────────────────────────── 裁判 Prompt ───────────────────────────

JUDGE_SYSTEM_PROMPT = """你是电商客服回复的幻觉审计员。给定三元组（用户问题、客服回复、知识库条目），
判断回复是否包含知识库无法支撑的"幻觉"。严格按以下分类体系输出：

分类体系（types 可多选）：
- C1 事实矛盾：回复断言与 KB 明确记载直接冲突（数值、政策、材质、接口等）
- C2 无据虚构：编造 KB 中不存在的实体/入口/承诺（KB 无记载或显式否认）
  注意区分：KB"未标注某参数"时回复肯定该参数 → C2；KB 完全无关的提问被回复强加关系 → C2
- C3 能力越界：声称执行了系统不具备的接口能力（查物流/查退款/改订单/升级工单等）
- C4 安全误导：对健康/安全关键信息给出误导性保证（孕妇可用、无副作用等）
- C5 信息遗漏：遗漏 KB 中的关键限定信息导致建议失真（边界模糊，谨慎判定）

判定规则：
1. 逐句校验回复中的每个事实性断言；部分正确部分错误时 partial=true，severity 降级为 medium
2. evidence 必须引用 KB 原文片段与回复原文对照；给不出 KB 依据的幻觉指控无效
3. 回复与 KB 一致、或仅做 KB 内容的合理转述 → hallucination=false
4. 不确定时倾向 hallucination=false（宁缺勿滥），但对 C4 安全类宁可多报
5. severity：C4=critical；C1/C2/C3=high（partial 时 medium）；C5=low

只输出 JSON，不要任何其他文字：
{"hallucination": bool, "types": ["C1"], "severity": "critical|high|medium|low",
 "partial": bool, "evidence": ["回复称…；KB 记载…"], "confidence": 0.0-1.0, "reasoning": "一句话理由"}"""


def build_judge_user_prompt(item: dict) -> str:
    return (
        f"用户问题：{item['user_question']}\n"
        f"客服回复：{item['system_reply']}\n"
        f"知识库：{item['knowledge_base']}\n"
        f"请输出 JSON 判定。可用分类：{TYPE_LABELS}"
    )


@dataclass
class JudgeVerdict:
    hits: list[RuleHit] = field(default_factory=list)
    fallback: bool = False      # 裁判不可用/解析失败 → 仲裁层降级为仅规则结果
    raw: dict | None = None     # 原始判定（写入结果供审计）


# ─────────────────────── Mock：确定性模拟裁判 ───────────────────────


class SimulatedJudge:
    """确定性启发式模拟裁判（mock 模式）。

    覆盖语义类 case 的典型模式，与真实 LLM 裁判共享输出契约：
    mock 模式保证零依赖可复现；real 模式由 LLM 承担泛化判定。
    """

    _DAYS_POLICY = re.compile(r"(\d+)\s*天无理由")
    _BLUETOOTH = re.compile(r"蓝牙\s*(\d(?:\.\d)?)")
    _SHIP_HOURS = re.compile(r"(\d+)\s*小时内发货")
    _REPLY_LEATHER = re.compile(r"头层牛皮|真皮|牛皮")
    _KB_SYNTHETIC = re.compile(r"PU|合成革|超纤|帆布|布面")
    _KB_WARRANTY_MONTH = re.compile(r"保修期[:：]?\s*(\d+)\s*个?月")
    _REPLY_WARRANTY = re.compile(r"保修期[^。]*?(\d+)\s*年|保修期[^。]*?(两|二|三)\s*年")
    _CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5}

    def judge(self, item: dict) -> JudgeVerdict:
        kb, reply = item["knowledge_base"], item["system_reply"]
        hits: list[RuleHit] = []

        # 1) 无理由退货天数冲突（C1）
        r_days = self._DAYS_POLICY.search(reply)
        k_days = self._DAYS_POLICY.search(kb)
        if r_days and k_days and r_days.group(1) != k_days.group(1):
            hits.append(RuleHit(
                rule="judge_policy_days",
                htype="C1", severity="high",
                evidence=f"回复称「{r_days.group(0)}」，KB 记载「{k_days.group(0)}」",
                confidence=0.9,
            ))

        # 2) 蓝牙版本冲突（C1）
        r_bt = self._BLUETOOTH.search(reply)
        k_bt = self._BLUETOOTH.search(kb)
        if r_bt and k_bt and r_bt.group(1) != k_bt.group(1):
            hits.append(RuleHit(
                rule="judge_bluetooth_version",
                htype="C1", severity="high",
                evidence=f"回复称蓝牙{r_bt.group(1)}，KB 记载蓝牙{k_bt.group(1)}",
                confidence=0.9,
            ))

        # 3) 发货时长冲突（C1）
        r_ship = self._SHIP_HOURS.search(reply)
        k_ship = self._SHIP_HOURS.search(kb)
        if r_ship and k_ship and r_ship.group(1) != k_ship.group(1):
            hits.append(RuleHit(
                rule="judge_shipping_hours",
                htype="C1", severity="high",
                evidence=f"回复称「{r_ship.group(0)}」，KB 记载「{k_ship.group(0)}」",
                confidence=0.9,
            ))

        # 4) 材质冲突（C1）
        if self._REPLY_LEATHER.search(reply) and self._KB_SYNTHETIC.search(kb):
            hits.append(RuleHit(
                rule="judge_material_conflict",
                htype="C1", severity="high",
                evidence=(
                    f"回复宣称真皮/牛皮，KB 记载材质为"
                    f"「{self._KB_SYNTHETIC.search(kb).group(0)}」系合成材质"
                ),
                confidence=0.9,
            ))

        # 5) 保修期冲突（C1）
        k_w = self._KB_WARRANTY_MONTH.search(kb)
        r_w = self._REPLY_WARRANTY.search(reply)
        if k_w and r_w:
            reply_months = None
            if r_w.group(1):
                reply_months = int(r_w.group(1)) * 12
            elif r_w.group(2) in self._CN_NUM:
                reply_months = self._CN_NUM[r_w.group(2)] * 12
            if reply_months and reply_months != int(k_w.group(1)):
                hits.append(RuleHit(
                    rule="judge_warranty_conflict",
                    htype="C1", severity="high",
                    evidence=f"回复称保修{r_w.group(0)[3:]}，KB 记载保修期{k_w.group(1)}个月",
                    confidence=0.9,
                ))

        raw = {"engine": "simulated", "reasoning": "确定性启发式模拟裁判", "hits": len(hits)}
        return JudgeVerdict(hits=hits, fallback=False, raw=raw)


# ─────────────────────── Real：LLM-as-Judge ───────────────────────


def _extract_json(text: str) -> dict:
    """从模型输出中提取 JSON（容忍 ```json 围栏与前后杂文）。"""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    obj = re.search(r"\{.*\}", text, re.DOTALL)
    if obj:
        return json.loads(obj.group(0))
    raise ValueError("no JSON object found in judge output")


_VALID_TYPES = {"C1", "C2", "C3", "C4", "C5"}


class RealJudge:
    """真实 LLM 裁判（OpenAI 兼容接口）。解析失败带错误上下文重试 1 次。"""

    MAX_RETRIES = 1

    def __init__(self) -> None:
        from langchain_openai import ChatOpenAI

        from app.config import settings

        self._llm = ChatOpenAI(
            model=settings.JUDGE_MODEL,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            temperature=settings.JUDGE_TEMPERATURE,
            timeout=30,
        )

    def judge(self, item: dict) -> JudgeVerdict:
        from langchain_core.messages import HumanMessage, SystemMessage


        messages = [
            SystemMessage(content=JUDGE_SYSTEM_PROMPT),
            HumanMessage(content=build_judge_user_prompt(item)),
        ]
        last_err: Exception | None = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                resp = self._llm.invoke(messages)
                verdict = _extract_json(resp.content)
                return self._to_hits(verdict)
            except Exception as exc:  # noqa: BLE001 — 网络/解析异常统一走降级链
                last_err = exc
                logger.warning("judge parse/call failed (attempt %s): %s", attempt + 1, exc)
                messages.append(HumanMessage(
                    content=f"上一次输出解析失败（{exc}）。请严格只输出符合 schema 的 JSON。"
                ))
        logger.error("judge fallback to rules-only: %s", last_err)
        return JudgeVerdict(hits=[], fallback=True,
                            raw={"engine": "llm", "error": str(last_err)})

    def _to_hits(self, verdict: dict) -> JudgeVerdict:
        """防护裁判自身幻觉：宣称幻觉但给不出 evidence → 判 NONE。"""
        if not verdict.get("hallucination"):
            return JudgeVerdict(hits=[], fallback=False, raw=verdict)
        evidence = [e for e in verdict.get("evidence", []) if isinstance(e, str) and e.strip()]
        if not evidence:
            return JudgeVerdict(hits=[], fallback=False, raw=verdict)
        types = [t for t in verdict.get("types", []) if t in _VALID_TYPES] or ["C1"]
        severity = verdict.get("severity") or "high"
        partial = bool(verdict.get("partial"))
        confidence = float(verdict.get("confidence", 0.85))
        hits = [
            RuleHit(
                rule="llm_judge",
                htype=t,
                severity=severity if len(types) == 1 else "high",
                evidence="；".join(evidence),
                confidence=max(0.5, min(confidence, 0.97)),
                partial=partial,
            )
            for t in types
        ]
        return JudgeVerdict(hits=hits, fallback=False, raw=verdict)
