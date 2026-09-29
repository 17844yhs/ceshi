"""CLI — 一键跑批 + 评测

用法：
  uv run python scripts/run_eval.py                # mock 模式
  uv run python scripts/run_eval.py --mode real    # 真实 LLM 裁判
  uv run python scripts/run_eval.py --limit 5      # 只跑前 5 条

产物：
  results/results.json      逐条检测结果
  results/eval_report.json  与 ground truth 对比的评测报告
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.core.detector import HallucinationDetector  # noqa: E402
from app.services.eval_service import evaluate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="HalluGuard 批量检测 + 评测")
    parser.add_argument("--mode", choices=["mock", "real"], help="覆盖 HALLU_MOCK")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0=全部）")
    args = parser.parse_args()

    if args.mode == "mock":
        settings.HALLU_MOCK = True
    elif args.mode == "real":
        settings.HALLU_MOCK = False

    detector = HallucinationDetector()
    items = json.loads((settings.DATA_DIR / "task4_replies.json").read_text(encoding="utf-8"))
    ground_truth = json.loads(
        (settings.DATA_DIR / "task4_ground_truth.json").read_text(encoding="utf-8")
    )
    if args.limit:
        items, ground_truth = items[: args.limit], ground_truth[: args.limit]

    results = detector.detect_batch(items)
    report = evaluate(results, ground_truth)

    settings.RESULTS_DIR.mkdir(exist_ok=True)
    results_path = settings.RESULTS_DIR / "results.json"
    report_path = settings.RESULTS_DIR / "eval_report.json"
    results_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report_path.write_text(
        json.dumps({**report, "mode": detector.mode}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 终端摘要表（截图用）
    print(f"\n=== HalluGuard 批量检测（mode={detector.mode}，n={len(results)}）===")
    print(f"{'ID':<5}{'判定':<10}{'分类':<18}{'严重度':<10}{'置信':<7}复核")
    for r in results:
        label = "幻觉" if r["label"] == "hallucination" else "正常"
        types = "+".join(r["type_labels"]) or "-"
        flag = "需人工" if r["needs_review"] else ""
        print(f"{r['id']:<5}{label:<10}{types:<18}{r['severity']:<10}{r['confidence']:<7}{flag}")

    c = report["confusion"]
    m = report["metrics"]
    print("\n--- 混淆矩阵 ---")
    print(f"TP={c['tp']}  FP={c['fp']}  FN={c['fn']}  TN={c['tn']}")
    print(
        f"Precision={m['precision']:.2%}  Recall={m['recall']:.2%}  "
        f"F1={m['f1']:.2%}  Accuracy={m['accuracy']:.2%}  分类对齐率={m['type_alignment']:.2%}"
    )
    print(f"\n产物：{results_path}\n      {report_path}")


if __name__ == "__main__":
    main()
