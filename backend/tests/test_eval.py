"""评测服务单元测试 — 指标计算与归因"""
from app.services.eval_service import evaluate


def _gt(id_, is_h, type_=None):
    return {"id": id_, "is_hallucination": is_h, "hallucination_type": type_, "detail": ""}


def _pred(id_, label, types):
    return {
        "id": id_,
        "label": label,
        "types": types,
        "severity": "high",
        "confidence": 0.9,
        "evidence": ["e"],
        "rule_hits": ["x"],
        "judge_fallback": False,
    }


class TestEvaluate:
    def test_perfect(self):
        gt = [_gt("a", True, "能力越界"), _gt("b", False)]
        pred = [_pred("a", "hallucination", ["C3"]), _pred("b", "none", [])]
        r = evaluate(pred, gt)
        assert r["confusion"] == {"tp": 1, "fp": 0, "fn": 0, "tn": 1}
        assert r["metrics"]["recall"] == 1.0
        assert r["metrics"]["precision"] == 1.0
        assert r["metrics"]["type_alignment"] == 1.0
        assert r["missed"] == [] and r["false_positives"] == []

    def test_fn_attributed(self):
        gt = [_gt("a", True, "信息遗漏")]
        pred = [_pred("a", "none", [])]
        r = evaluate(pred, gt)
        assert r["confusion"]["fn"] == 1
        assert "边界模糊" in r["missed"][0]["attribution"]

    def test_fp_attributed(self):
        gt = [_gt("a", False)]
        pred = [_pred("a", "hallucination", ["C5"])]
        r = evaluate(pred, gt)
        assert r["confusion"]["fp"] == 1
        assert "过度敏感" in r["false_positives"][0]["attribution"]

    def test_param_type_maps_to_c1_or_c2(self):
        # GT 参数编造 → {C1, C2}：预测 C2 也算分类对齐（h09 特例）
        gt = [_gt("a", True, "参数编造")]
        pred = [_pred("a", "hallucination", ["C2"])]
        r = evaluate(pred, gt)
        assert r["metrics"]["type_alignment"] == 1.0
