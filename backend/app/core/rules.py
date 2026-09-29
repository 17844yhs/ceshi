"""规则层 — 高精度确定性检查（零 LLM 成本）

设计原则：规则能确定性兜底的绝不过模型。
  - C3 能力越界：KB 声明能力缺失 + 回复能力声明词 → 确定性命中
  - C4 安全误导：KB 人群警示 + 回复绿灯话术
  - C5 信息遗漏：KB 反馈统计 + 回复绝对化断言（低置信，进人工复核）
  - 结构化 C1/C2：集合成员校验（优惠券/快递）、字段冲突（接口）、
    "KB 显式否认 X + 回复肯定 X"（否定前缀感知）、地址泄露等

每条规则返回 RuleHit 列表；未命中返回空列表。
"""
import re
from dataclasses import dataclass, field

from app.core.taxonomy import HalluType

# 否定前缀字符（窗口内出现即视为否定语境）
_NEGATION_CHARS = "不无没未暂别勿非难"


@dataclass
class RuleHit:
    rule: str            # 规则名（可追溯）
    htype: str           # HalluType value
    severity: str
    evidence: str        # 人类可读证据（引用 KB / 回复原文）
    confidence: float
    partial: bool = False  # 部分正确部分错误（如 h04）
    meta: dict = field(default_factory=dict)


def has_affirm(text: str, keyword: str, window: int = 3) -> bool:
    """否定前缀感知的肯定判断：keyword 出现且紧邻前缀无否定字。"""
    for m in re.finditer(re.escape(keyword), text):
        prefix = text[max(0, m.start() - window): m.start()]
        if not any(ch in _NEGATION_CHARS for ch in prefix):
            return True
    return False


def _snippet(text: str, m: re.Match, pad: int = 12) -> str:
    s = max(0, m.start() - pad)
    e = min(len(text), m.end() + pad)
    return text[s:e].strip()


# ─────────────────────────── C3 能力越界 ───────────────────────────

_KB_NO_CAPABILITY = re.compile(r"未接入|不具备|未对接|没有接入")
_REPLY_CAPABILITY_CLAIM = re.compile(
    r"帮您查|我查了|查到了|查了下|已帮您|已修改|已经修改|帮您改了|升级为|已升级|已经将.{0,8}升级|已提交|已退款"
)


def rule_capability_overreach(item: dict) -> list[RuleHit]:
    """KB 明确声明未接入某接口/不具备某功能，回复却声称已执行相关操作。"""
    kb, reply = item["knowledge_base"], item["system_reply"]
    kb_m = _KB_NO_CAPABILITY.search(kb)
    claim_m = _REPLY_CAPABILITY_CLAIM.search(reply)
    if kb_m and claim_m:
        return [
            RuleHit(
                rule="capability_overreach",
                htype=HalluType.CAPABILITY.value,
                severity="high",
                evidence=(
                    f"KB 声明能力缺失：「{_snippet(kb, kb_m)}」；"
                    f"回复却声称已执行：「{_snippet(reply, claim_m)}」"
                ),
                confidence=0.92,
            )
        ]
    return []


# ─────────────────────────── C4 安全误导 ───────────────────────────

_KB_SAFETY_WARN = re.compile(r"(孕妇|哺乳)[^。]{0,20}(咨询医生|不建议|慎用|谨慎|禁用)")
_REPLY_SAFETY_GREEN = re.compile(r"孕妇[^。]{0,12}(放心|可以|能用|安全|温和)")


def rule_safety_misguidance(item: dict) -> list[RuleHit]:
    """KB 对特定人群（孕妇等）有明确警示，回复给出绿灯话术。"""
    kb, reply = item["knowledge_base"], item["system_reply"]
    kb_m = _KB_SAFETY_WARN.search(kb)
    reply_m = _REPLY_SAFETY_GREEN.search(reply)
    if kb_m and reply_m:
        return [
            RuleHit(
                rule="safety_misguidance",
                htype=HalluType.SAFETY.value,
                severity="critical",
                evidence=(
                    f"KB 警示：「{_snippet(kb, kb_m)}」；"
                    f"回复绿灯话术：「{_snippet(reply, reply_m)}」"
                ),
                confidence=0.95,
            )
        ]
    return []


# ─────────────────────────── C5 信息遗漏 ───────────────────────────

_KB_FEEDBACK_STAT = re.compile(r"(评价|反馈)[^。]{0,20}(偏大|偏小)")
_REPLY_ABSOLUTE_FIT = re.compile(r"尺码标准|码数标准|不偏大|不偏小|正码|正合适")


def rule_omission_absolute_claim(item: dict) -> list[RuleHit]:
    """KB 含用户反馈统计（如 30% 反馈偏大），回复做绝对化断言。

    边界模糊类：漏报风险与误报风险并存，置信度刻意压低进人工复核。
    """
    kb, reply = item["knowledge_base"], item["system_reply"]
    kb_m = _KB_FEEDBACK_STAT.search(kb)
    reply_m = _REPLY_ABSOLUTE_FIT.search(reply)
    if kb_m and reply_m:
        return [
            RuleHit(
                rule="omission_absolute_claim",
                htype=HalluType.OMISSION.value,
                severity="low",
                evidence=(
                    f"KB 记载用户反馈：「{_snippet(kb, kb_m)}」；"
                    f"回复绝对化断言：「{_snippet(reply, reply_m)}」，遗漏关键限定信息"
                ),
                confidence=0.55,  # 模糊带：遗漏≠编造，需人工复核
                meta={"needs_review": True},
            )
        ]
    return []


# ─────────────────────── 结构化 C1/C2 检查 ───────────────────────

_COUPON = re.compile(r"满(\d+)减(\d+)")
_COURIER = re.compile(r"中通|韵达|圆通|顺丰|申通|邮政|京东|极兔")
_INTERFACE_TOKEN = re.compile(r"USB-?A|USB-?C|Type-?C|Lightning|Micro-?USB", re.IGNORECASE)
_KB_INTERFACE_FIELD = re.compile(r"接口类型[:：]\s*([^。]+)")


_KB_DENIED_COUPON = re.compile(r"无满(\d+)减(\d+)的?(?:活动|券)")


def rule_coupon_not_listed(item: dict) -> list[RuleHit]:
    """回复宣称的满减券不在 KB 优惠活动集合中 → C2 无据虚构。

    注意：KB 可能显式否认某券（"无满300减50的活动"），该表述同样含
    满300减50 字样，必须先从 KB 提供的券集合中剔除，否则会把否认当提供。
    """
    kb, reply = item["knowledge_base"], item["system_reply"]
    kb_coupons = set(_COUPON.findall(kb)) - set(_KB_DENIED_COUPON.findall(kb))
    reply_coupons = set(_COUPON.findall(reply))
    if kb_coupons and reply_coupons and not reply_coupons.issubset(kb_coupons):
        bogus = reply_coupons - kb_coupons
        return [
            RuleHit(
                rule="coupon_not_listed",
                htype=HalluType.FABRICATION.value,
                severity="high",
                evidence=(
                    f"回复宣称优惠「{'、'.join('满%s减%s' % c for c in sorted(bogus))}」，"
                    f"KB 优惠活动仅含「{'、'.join('满%s减%s' % c for c in sorted(kb_coupons))}」"
                ),
                confidence=0.9,
            )
        ]
    return []


def rule_courier_not_listed(item: dict) -> list[RuleHit]:
    """回复宣称的快递公司不在 KB 合作快递集合中 → C1 事实矛盾。"""
    kb, reply = item["knowledge_base"], item["system_reply"]
    kb_couriers = set(_COURIER.findall(kb))
    reply_couriers = set(_COURIER.findall(reply))
    if kb_couriers and reply_couriers and not reply_couriers.issubset(kb_couriers):
        bogus = reply_couriers - kb_couriers
        return [
            RuleHit(
                rule="courier_not_listed",
                htype=HalluType.CONTRADICTION.value,
                severity="high",
                evidence=(
                    f"回复宣称使用「{'、'.join(sorted(bogus))}」，"
                    f"KB 合作快递为「{'、'.join(sorted(kb_couriers))}」"
                ),
                confidence=0.88,
            )
        ]
    return []


def rule_interface_conflict(item: dict) -> list[RuleHit]:
    """KB『接口类型』字段与回复宣称的接口冲突 → C1（字段作用域限定，防 KB 他处提及误报）。"""
    kb, reply = item["knowledge_base"], item["system_reply"]
    field_m = _KB_INTERFACE_FIELD.search(kb)
    if not field_m:
        return []
    kb_types = set(_INTERFACE_TOKEN.findall(field_m.group(1)))
    reply_types = set(_INTERFACE_TOKEN.findall(reply))
    if kb_types and reply_types and not reply_types.issubset(kb_types):
        bogus = reply_types - kb_types
        return [
            RuleHit(
                rule="interface_conflict",
                htype=HalluType.CONTRADICTION.value,
                severity="high",
                evidence=(
                    f"回复宣称接口为「{'、'.join(sorted(bogus))}」，"
                    f"KB 接口类型字段记载「{field_m.group(1).strip()}」"
                ),
                confidence=0.9,
            )
        ]
    return []


# ── KB 显式否认 X + 回复肯定 X（否定前缀感知）──

_KB_DENY_SUPPORT = re.compile(r"(?:暂不|不)支持\s*([\u4e00-\u9fa5A-Za-z0-9]{2,12})")
_KB_UNANNOTATED = re.compile(r"未标注\s*([\u4e00-\u9fa5A-Za-z0-9]{2,12})")
_KB_NO_POLICY = re.compile(r"(?:当前)?无\s*([\u4e00-\u9fa5A-Za-z]{2,10}?)政策")
_KB_ONLINE_ONLY = re.compile(r"纯线上|无线下门店|没有线下")
_REPLY_STORE_CLAIM = re.compile(r"线下(体验)?店|门店查询|到店")
_KB_NO_RELATION = re.compile(r"未提及[^。]{0,20}(关联|旗下|合作|关系)")
_REPLY_RELATION_CLAIM = re.compile(r"旗下|子品牌|同一家|关联品牌|属于[^。]{0,6}品牌")
_KB_SUPPORTED = re.compile(r"支持\s*([\u4e00-\u9fa5]{2,10})")


def _kb_supported_affirmed_in_reply(kb: str, reply: str) -> bool:
    """partial 检测：回复同时肯定了 KB 支持的事项（部分正确部分错误）。"""
    return any(has_affirm(reply, s) for s in _KB_SUPPORTED.findall(kb))


def rule_affirm_denied_feature(item: dict) -> list[RuleHit]:
    """KB 显式否认（不支持X / 未标注X / 无X政策），回复肯定 X。"""
    kb, reply = item["knowledge_base"], item["system_reply"]
    hits: list[RuleHit] = []

    m = _KB_DENY_SUPPORT.search(kb)
    if m and has_affirm(reply, m.group(1)):
        partial = _kb_supported_affirmed_in_reply(kb, reply)
        hits.append(
            RuleHit(
                rule="affirm_denied_support",
                htype=HalluType.CONTRADICTION.value,
                # 部分正确部分错误 → 降级 MEDIUM
                severity="medium" if partial else "high",
                evidence=(
                    f"KB 明确「不支持{m.group(1)}」，回复却肯定提供；"
                    + ("但回复同时正确说明了 KB 支持的部分（partial）" if partial else "")
                ).rstrip("；,， "),
                confidence=0.85,
                partial=partial,
            )
        )

    m = _KB_UNANNOTATED.search(kb)
    if m and has_affirm(reply, m.group(1)):
        hits.append(
            RuleHit(
                rule="affirm_unannotated_feature",
                htype=HalluType.FABRICATION.value,
                severity="high",
                evidence=(
                    f"KB 标注「未标注{m.group(1)}」（未记载≠支持），"
                    f"回复却肯定支持并展开说明"
                ),
                confidence=0.85,
            )
        )

    m = _KB_NO_POLICY.search(kb)
    if m:
        concept = m.group(1).rstrip("优惠")
        if concept and has_affirm(reply, concept) and re.search(r"折|优惠|认证|减免", reply):
            hits.append(
                RuleHit(
                    rule="affirm_denied_policy",
                    htype=HalluType.FABRICATION.value,
                    severity="high",
                    evidence=f"KB 明确「无{m.group(1)}政策」，回复却宣称存在并给出使用入口",
                    confidence=0.88,
                )
            )
    return hits


def rule_online_only_store_claim(item: dict) -> list[RuleHit]:
    """KB 声明纯线上品牌/无线下门店，回复宣称线下门店。"""
    kb, reply = item["knowledge_base"], item["system_reply"]
    if _KB_ONLINE_ONLY.search(kb) and _REPLY_STORE_CLAIM.search(reply):
        m = _REPLY_STORE_CLAIM.search(reply)
        return [
            RuleHit(
                rule="online_only_store_claim",
                htype=HalluType.FABRICATION.value,
                severity="high",
                evidence=(
                    f"KB 声明「纯线上电商品牌，无线下门店」，"
                    f"回复却宣称「{_snippet(reply, m)}」"
                ),
                confidence=0.88,
            )
        ]
    return []


def rule_brand_relation_fabrication(item: dict) -> list[RuleHit]:
    """KB 未提及品牌关联，回复杜撰关联关系。"""
    kb, reply = item["knowledge_base"], item["system_reply"]
    if _KB_NO_RELATION.search(kb) and _REPLY_RELATION_CLAIM.search(reply):
        m = _REPLY_RELATION_CLAIM.search(reply)
        return [
            RuleHit(
                rule="brand_relation_fabrication",
                htype=HalluType.FABRICATION.value,
                severity="high",
                evidence=(
                    f"KB「品牌介绍中未提及其他品牌关联关系」，"
                    f"回复杜撰「{_snippet(reply, m)}」"
                ),
                confidence=0.85,
            )
        ]
    return []


# ── 退货地址泄露 ──

_KB_ADDRESS_VIA_SMS = re.compile(r"短信方式发送|自动匹配|口头告知|不可直接提供")
_REPLY_CONCRETE_ADDRESS = re.compile(r"[\u4e00-\u9fa5]{2,8}(?:省|市)[\u4e00-\u9fa5]{2,10}(?:区|县)?[\u4e00-\u9fa5]{2,10}(?:路|街|道)\d+号")


def rule_address_disclosure(item: dict) -> list[RuleHit]:
    """KB 规定退货地址由系统短信下发，回复口头杜撰具体地址。"""
    kb, reply = item["knowledge_base"], item["system_reply"]
    if _KB_ADDRESS_VIA_SMS.search(kb):
        m = _REPLY_CONCRETE_ADDRESS.search(reply)
        if m:
            return [
                RuleHit(
                    rule="address_disclosure",
                    htype=HalluType.FABRICATION.value,
                    severity="high",
                    evidence=(
                        "KB 规定退货地址需系统自动匹配后以短信发送，"
                        f"回复却杜撰具体地址「{m.group(0)}」"
                    ),
                    confidence=0.9,
                )
            ]
    return []


# ─────────────────────────── 规则注册表 ───────────────────────────

RULES = [
    rule_capability_overreach,
    rule_safety_misguidance,
    rule_omission_absolute_claim,
    rule_coupon_not_listed,
    rule_courier_not_listed,
    rule_interface_conflict,
    rule_affirm_denied_feature,
    rule_online_only_store_claim,
    rule_brand_relation_fabrication,
    rule_address_disclosure,
]


def run_rules(item: dict) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for fn in RULES:
        hits.extend(fn(item))
    return hits
