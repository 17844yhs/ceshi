"""端到端测试 — 20 条数据集 mock 模式全流程（零外部依赖）"""
import json
from pathlib import Path

import pytest

from app.core.detector import HallucinationDetector
from app.services.eval_service import evaluate

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def dataset():
    replies = json.loads((DATA_DIR / "task4_replies.json").read_text(encoding="utf-8"))
    gt = json.loads((DATA_DIR / "task4_ground_truth.json").read_text(encoding="utf-8"))
    return replies, gt


@pytest.fixture(scope="module")
def eval_report(dataset):
    replies, gt = dataset
    detector = HallucinationDetector()
    results = detector.detect_batch(replies)
    return detector, results, evaluate(results, gt)


class TestEndToEnd:
    def test_all_ids_covered(self, eval_report):
        _, results, _ = eval_report
        assert [r["id"] for r in results] == [f"h{i:02d}" for i in range(1, 21)]

    def test_perfect_binary_detection(self, eval_report):
        _, _, report = eval_report
        assert report["confusion"]["fn"] == 0, "存在漏检"
        assert report["confusion"]["fp"] == 0, "存在误报"
        assert report["metrics"]["recall"] == 1.0
        assert report["metrics"]["precision"] == 1.0

    def test_expected_classes(self, eval_report):
        _, results, _ = eval_report
        by_id = {r["id"]: r for r in results}
        assert by_id["h13"]["types"] == ["C4"] and by_id["h13"]["severity"] == "critical"
        assert by_id["h03"]["types"] == ["C3"]
        assert by_id["h01"]["types"] == ["C1"]
        assert by_id["h05"]["types"] == ["C2"]
        assert by_id["h20"]["types"] == ["C5"] and by_id["h20"]["needs_review"] is True
        assert by_id["h12"]["label"] == "none"
        assert by_id["h16"]["label"] == "none"

    def test_partial_case_h04(self, eval_report):
        _, results, _ = eval_report
        h04 = next(r for r in results if r["id"] == "h04")
        assert h04["partial"] is True and h04["severity"] == "medium"

    def test_results_complete_schema(self, eval_report):
        _, results, _ = eval_report
        required = {"id", "label", "types", "severity", "confidence", "evidence",
                    "rule_hits", "judge_fallback", "mode", "needs_review"}
        assert all(required <= set(r) for r in results)
