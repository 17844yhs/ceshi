"""评测服务 — 与人工标注对齐：混淆矩阵、宏平均 P/R/F1、漏检/误报归因

GT 标签 → 分类体系映射（9 种零散标签收敛为 5 类）：
  政策编造/政策偏差/参数编造 → C1（参数编造特例：KB 未记载而回复断言 → C2，
  如 h09 NFC，故映射为 {C1, C2} 二者命中其一即视为分类对齐）
  优惠编造/信息编造 → C2 ｜ 能力越界 → C3 ｜ 安全误导 → C4 ｜ 信息遗漏 → C5
"""
from __future__ import annotations

GT_TYPE_MAP: dict[str, list[str]] = {
    "政策编造": ["C1"],
    "政策偏差": ["C1"],
    "参数编造": ["C1", "C2"],
    "优惠编造": ["C2"],
    "信息编造": ["C2"],
    "能力越界": ["C3"],
    "安全误导": ["C4"],
    "信息遗漏": ["C5"],
}


def _safe_div(a: float, b: float) -> float:
    return round(a / b, 4) if b else 0.0


def _attribute_fn(gt_item: dict, pred_item: dict, kind: str) -> str:
    """误判归因：给漏检（fn）/误报（fp）打原因标签。"""
    gt_type = gt_item.get("hallucination_type") or ""
    if kind == "fn":
        if gt_type == "信息遗漏":
            return "边界模糊：遗漏≠编造，依赖『KB 反馈统计 + 回复绝对化断言』模式识别，易漏检"
        if not pred_item.get("pred_types"):
            return "规则未覆盖该模式且裁判判为一致：需扩充规则库或优化裁判 prompt"
        return "规则与裁判均未命中：检查证据抽取覆盖面"
    # fp
    if pred_item.get("pred_types") == ["C5"]:
        return "过度敏感：把『未提及』当『遗漏』，需收紧绝对化断言匹配"
    if pred_item.get("judge_fallback"):
        return "裁判降级：仅凭规则层误报，需检查规则精确率"
    return "规则/裁判误伤：KB 中性表述被误读为矛盾，需增加否定语境判定"


def evaluate(results: list[dict], ground_truth: list[dict]) -> dict:
    gt_by_id = {g["id"]: g for g in ground_truth}

    tp = fp = tn = fn = 0
    per_item: list[dict] = []
    type_aligned = 0

    for pred in results:
        gt = gt_by_id.get(pred["id"])
        if gt is None:
            continue
        pred_hallu = pred["label"] == "hallucination"
        gt_hallu = bool(gt["is_hallucination"])

        if gt_hallu and pred_hallu:
            tp += 1
            mapped = GT_TYPE_MAP.get(gt.get("hallucination_type") or "", [])
            ok = bool(set(pred["types"]) & set(mapped))
            type_aligned += int(ok)
        elif not gt_hallu and pred_hallu:
            fp += 1
        elif gt_hallu and not pred_hallu:
            fn += 1
        else:
            tn += 1

        per_item.append({
            "id": pred["id"],
            "gt_hallucination": gt_hallu,
            "gt_type": gt.get("hallucination_type"),
            "gt_detail": gt.get("detail"),
            "pred_label": pred["label"],
            "pred_types": pred["types"],
            "pred_severity": pred["severity"],
            "pred_confidence": pred["confidence"],
            "pred_evidence": pred["evidence"][:1],
            "binary_match": pred_hallu == gt_hallu,
            "type_match": (pred_hallu and gt_hallu
                           and bool(set(pred["types"]) & set(GT_TYPE_MAP.get(gt.get("hallucination_type") or "", [])))),
        })

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    accuracy = _safe_div(tp + tn, tp + tn + fp + fn)

    fn_list = [
        {**it, "attribution": _attribute_fn(gt_by_id[it["id"]], it, "fn")}
        for it in per_item if it["gt_hallucination"] and not it["pred_label"] == "hallucination"
    ]
    fp_list = [
        {**it, "attribution": _attribute_fn(gt_by_id[it["id"]], it, "fp")}
        for it in per_item if not it["gt_hallucination"] and it["pred_label"] == "hallucination"
    ]

    # GT 侧分类分布 vs 预测侧分类分布
    gt_type_dist: dict[str, int] = {}
    for g in ground_truth:
        if g["is_hallucination"]:
            gt_type_dist[g["hallucination_type"]] = gt_type_dist.get(g["hallucination_type"], 0) + 1
    pred_type_dist: dict[str, int] = {}
    for r in results:
        for t in r["types"]:
            pred_type_dist[t] = pred_type_dist.get(t, 0) + 1

    return {
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "metrics": {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "accuracy": accuracy,
            "type_alignment": _safe_div(type_aligned, tp) if tp else 0.0,
        },
        "per_item": per_item,
        "missed": fn_list,
        "false_positives": fp_list,
        "gt_type_dist": gt_type_dist,
        "pred_type_dist": pred_type_dist,
    }
