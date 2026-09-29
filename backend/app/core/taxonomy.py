"""幻觉分类体系 — 5 类 × 3 级严重度

由 ground truth 的 9 种零散标签 MECE 归纳而来：
  政策编造/政策偏差/参数编造(部分) → C1 事实矛盾
  优惠编造/信息编造/参数编造(KB无记载) → C2 无据虚构
  能力越界 → C3
  安全误导 → C4（CRITICAL，健康风险最高）
  信息遗漏 → C5（LOW，边界模糊）
"""
from enum import Enum


class HalluType(str, Enum):
    CONTRADICTION = "C1"   # 事实矛盾：回复断言与 KB 明确记载直接冲突
    FABRICATION = "C2"     # 无据虚构：编造 KB 中不存在的实体/入口/承诺
    CAPABILITY = "C3"      # 能力越界：声称执行了系统不具备的接口能力
    SAFETY = "C4"          # 安全误导：涉及健康/安全的关键信息误导
    OMISSION = "C5"        # 信息遗漏：遗漏 KB 关键限定信息致建议失真
    NONE = "NONE"          # 无幻觉


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


TYPE_LABELS: dict[str, str] = {
    HalluType.CONTRADICTION.value: "事实矛盾",
    HalluType.FABRICATION.value: "无据虚构",
    HalluType.CAPABILITY.value: "能力越界",
    HalluType.SAFETY.value: "安全误导",
    HalluType.OMISSION.value: "信息遗漏",
}

# 各类型默认严重度（业务风险：健康安全 > 资损/能力欺骗 > 一般事实错误 > 建议失真）
TYPE_DEFAULT_SEVERITY: dict[str, Severity] = {
    HalluType.CONTRADICTION.value: Severity.HIGH,
    HalluType.FABRICATION.value: Severity.HIGH,
    HalluType.CAPABILITY.value: Severity.HIGH,
    HalluType.SAFETY.value: Severity.CRITICAL,
    HalluType.OMISSION.value: Severity.LOW,
}

_SEVERITY_ORDER: dict[str, int] = {
    Severity.LOW.value: 0,
    Severity.MEDIUM.value: 1,
    Severity.HIGH.value: 2,
    Severity.CRITICAL.value: 3,
}


def severity_rank(sev: str) -> int:
    return _SEVERITY_ORDER.get(sev, -1)


def max_severity(a: str, b: str) -> str:
    return a if severity_rank(a) >= severity_rank(b) else b


def default_severity(htype: str) -> str:
    return TYPE_DEFAULT_SEVERITY.get(htype, Severity.HIGH.value)


# 置信度低于该阈值的样本进入人工复核队列（h20 类模糊带落在 0.4-0.6）
REVIEW_THRESHOLD = 0.7
