"""单元测试 — 规则层各检查器的命中与防误报"""

from app.core.rules import (
    rule_address_disclosure,
    rule_affirm_denied_feature,
    rule_capability_overreach,
    rule_coupon_not_listed,
    rule_courier_not_listed,
    rule_interface_conflict,
    rule_omission_absolute_claim,
    rule_online_only_store_claim,
    rule_safety_misguidance,
)


def _item(kb: str, reply: str, q: str = "q") -> dict:
    return {"id": "t", "user_question": q, "system_reply": reply, "knowledge_base": kb}


class TestCapability:
    def test_hit(self):
        it = _item("无（客服系统未接入物流查询接口）", "我帮您查了一下，包裹在南京转运中心。")
        hits = rule_capability_overreach(it)
        assert len(hits) == 1 and hits[0].htype == "C3" and hits[0].severity == "high"

    def test_no_kb_marker_no_hit(self):
        it = _item("物流由商家发货", "我帮您查了一下，包裹在南京转运中心。")
        assert rule_capability_overreach(it) == []


class TestSafety:
    def test_hit(self):
        it = _item(
            "含视黄醇衍生物，孕妇及哺乳期女性建议咨询医生后使用。",
            "孕妇可以放心使用，成分温和。",
        )
        hits = rule_safety_misguidance(it)
        assert len(hits) == 1 and hits[0].htype == "C4" and hits[0].severity == "critical"

    def test_reply_consistent_no_hit(self):
        it = _item("孕妇建议咨询医生后使用。", "孕妇建议先咨询医生再决定哦。")
        assert rule_safety_misguidance(it) == []


class TestOmission:
    def test_hit_low_confidence_needs_review(self):
        it = _item(
            "用户评价汇总：约30%的用户反馈偏大半码，建议脚瘦的用户选小半码。",
            "这款鞋尺码标准，不偏大也不偏小。",
        )
        hits = rule_omission_absolute_claim(it)
        assert hits and hits[0].htype == "C5" and hits[0].confidence < 0.7
        assert hits[0].meta["needs_review"] is True


class TestCoupon:
    def test_hit(self):
        it = _item("当前优惠活动：满200减20、满500减60。", "有一张满300减50的店铺优惠券。")
        hits = rule_coupon_not_listed(it)
        assert len(hits) == 1 and hits[0].htype == "C2"

    def test_reply_subset_no_hit(self):
        it = _item("当前优惠活动：满200减20、满500减60。", "可以领满200减20的券。")
        assert rule_coupon_not_listed(it) == []


class TestCourier:
    def test_hit(self):
        it = _item("合作快递：中通/韵达/圆通。", "一般使用顺丰快递。")
        hits = rule_courier_not_listed(it)
        assert len(hits) == 1 and hits[0].htype == "C1"


class TestInterface:
    def test_hit_scoped_to_field(self):
        # KB 他处提到 Type-C（充电线），但接口类型字段是 USB-A —— 作用域限定防误报为一致
        it = _item("接口类型：USB-A输出。附带一根USB-A to Type-C充电线。", "这款充电头是Type-C接口。")
        hits = rule_interface_conflict(it)
        assert len(hits) == 1 and hits[0].htype == "C1"


class TestAffirmDenied:
    def test_paper_invoice_hit_with_partial(self):
        it = _item(
            "支持电子发票，下单后在订单详情页申请。暂不支持纸质发票。",
            "支持电子发票和纸质发票。",
        )
        hits = rule_affirm_denied_feature(it)
        assert len(hits) == 1
        assert hits[0].htype == "C1" and hits[0].partial is True
        assert hits[0].severity == "medium"

    def test_negation_aware_no_hit(self):
        # h12：回复也说"不支持"，不能因子串"支持货到付款"误报
        it = _item("支付方式：微信支付、支付宝。不支持货到付款。", "目前不支持货到付款，支持微信和支付宝。")
        assert rule_affirm_denied_feature(it) == []

    def test_unannotated_feature_hit(self):
        it = _item("产品参数中未标注NFC功能。", "支持的，这款手机支持NFC功能。")
        hits = rule_affirm_denied_feature(it)
        assert len(hits) == 1 and hits[0].htype == "C2"

    def test_no_student_policy_hit(self):
        it = _item("当前无学生优惠政策。", "凭学生证可以享受9折优惠。")
        hits = rule_affirm_denied_feature(it)
        assert len(hits) == 1 and hits[0].htype == "C2"


class TestStoreAndBrand:
    def test_online_only_hit(self):
        it = _item("本品牌为纯线上电商品牌，无线下门店。", "我们在北上广深都有线下体验店。")
        hits = rule_online_only_store_claim(it)
        assert len(hits) == 1 and hits[0].htype == "C2"

    def test_brand_relation_hit(self):
        it = _item("品牌介绍中未提及其他品牌关联关系。", "我们是XX品牌旗下的子品牌。")
        hits = rule_affirm_denied_feature(it) + __import__(
            "app.core.rules", fromlist=["rule_brand_relation_fabrication"]
        ).rule_brand_relation_fabrication(it)
        assert any(h.htype == "C2" for h in hits)


class TestAddress:
    def test_hit(self):
        it = _item(
            "退货地址需由客服系统根据订单信息自动匹配后以短信方式发送。人工客服不可口头告知退货地址。",
            "退货请寄到：浙江省杭州市西湖区文三路478号 客服仓库 张经理收。",
        )
        hits = rule_address_disclosure(it)
        assert len(hits) == 1 and hits[0].htype == "C2"

    def test_kb_without_sms_rule_no_hit(self):
        # h14 类：回复含地址但 KB 并无"短信下发"规定 → 地址规则不应命中（能力越界规则负责）
        it = _item("无（客服系统未接入订单修改接口，需人工后台操作）", "已帮您修改为新地址：北京市朝阳区建国路88号。")
        assert rule_address_disclosure(it) == []
