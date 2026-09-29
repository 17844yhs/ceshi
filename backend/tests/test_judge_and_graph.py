"""单元测试 — Mock 裁判（确定性模拟）与仲裁层"""
from app.core.detector import HallucinationDetector
from app.core.llm_judge import SimulatedJudge
from app.graph.workflow import build_detection_graph


def _item(kb: str, reply: str, q: str = "q", id_: str = "t") -> dict:
    return {"id": id_, "user_question": q, "system_reply": reply, "knowledge_base": kb}


class TestSimulatedJudge:
    def test_policy_days(self):
        v = SimulatedJudge().judge(
            _item("普通商品支持7天无理由退货。", "全品类支持30天无理由退货。")
        )
        assert any(h.rule == "judge_policy_days" for h in v.hits)

    def test_bluetooth(self):
        v = SimulatedJudge().judge(_item("蓝牙5.0。", "采用蓝牙5.3版本。"))
        assert any(h.rule == "judge_bluetooth_version" for h in v.hits)

    def test_shipping_hours(self):
        v = SimulatedJudge().judge(_item("下单后24小时内发货。", "下单后48小时内发货。"))
        assert any(h.rule == "judge_shipping_hours" for h in v.hits)

    def test_material_and_warranty(self):
        v = SimulatedJudge().judge(_item("材质：PU合成革。保修期：6个月。", "头层牛皮制作，保修期为两年。"))
        rules = {h.rule for h in v.hits}
        assert "judge_material_conflict" in rules and "judge_warranty_conflict" in rules

    def test_consistent_no_hit(self):
        v = SimulatedJudge().judge(
            _item("支持微信支付、支付宝。不支持货到付款。", "不支持货到付款，支持微信和支付宝。")
        )
        assert v.hits == []


class TestGraph:
    def test_graph_runs_and_reconciles(self):
        graph = build_detection_graph()
        # 同时命中规则层（能力越界）与裁判层无命中 → 仅规则
        state = graph.invoke(
            {"item": _item("无（客服系统未接入物流查询接口）", "我帮您查了一下，包裹在南京。", id_="gx")}
        )
        result = state["result"]
        assert result["label"] == "hallucination"
        assert result["types"] == ["C3"]
        assert result["confidence"] >= 0.9

    def test_none_verdict(self):
        graph = build_detection_graph()
        state = graph.invoke(
            {"item": _item("商品图片可能与实物存在轻微色差，请以实物为准。", "可能有轻微色差，以实物为准。", id_="gn")}
        )
        assert state["result"]["label"] == "none"


class TestDetectorEndToEndSample:
    def test_detect_attaches_mode(self):
        det = HallucinationDetector()
        r = det.detect(_item("支持电子发票。暂不支持纸质发票。", "支持电子发票和纸质发票。", id_="dm"))
        assert r["mode"] == det.mode
        assert r["label"] == "hallucination"
        assert r["partial"] is True and r["severity"] == "medium"
