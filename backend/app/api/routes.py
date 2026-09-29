"""REST API — 单条检测 / 批量检测 / 评测对比 / 健康检查"""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from app.config import settings
from app.core.detector import HallucinationDetector
from app.services.eval_service import evaluate

bp = Blueprint("api", __name__, url_prefix="/api")

_detector_cache: dict[bool, HallucinationDetector] = {}


def _get_detector() -> HallucinationDetector:
    if settings.HALLU_MOCK not in _detector_cache:
        _detector_cache[settings.HALLU_MOCK] = HallucinationDetector()
    return _detector_cache[settings.HALLU_MOCK]


def _load_replies() -> list[dict]:
    path = settings.DATA_DIR / "task4_replies.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_ground_truth() -> list[dict]:
    path = settings.DATA_DIR / "task4_ground_truth.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@bp.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "mode": "mock" if settings.HALLU_MOCK else "real",
        "judge_model": None if settings.HALLU_MOCK else settings.JUDGE_MODEL,
    })


@bp.post("/detect")
def detect_single():
    body = request.get_json(silent=True) or {}
    for field in ("system_reply", "knowledge_base"):
        if not body.get(field):
            return jsonify({"error": f"missing field: {field}"}), 400
    item = {
        "id": body.get("id"),
        "user_question": body.get("user_question", ""),
        "system_reply": body["system_reply"],
        "knowledge_base": body["knowledge_base"],
    }
    return jsonify(_get_detector().detect(item))


@bp.post("/batch")
def detect_batch():
    detector = _get_detector()
    items = _load_replies()
    results = detector.detect_batch(items)
    # 附上原文，供看板做 KB vs 回复对照
    for item, r in zip(items, results, strict=True):
        r["question"] = item["user_question"]
        r["reply"] = item["system_reply"]
        r["kb"] = item["knowledge_base"]
    return jsonify({
        "mode": detector.mode,
        "total": len(results),
        "hallucination_count": sum(1 for r in results if r["label"] == "hallucination"),
        "needs_review_count": sum(1 for r in results if r["needs_review"]),
        "results": results,
    })


@bp.get("/eval")
def eval_against_gt():
    detector = _get_detector()
    results = detector.detect_batch(_load_replies())
    report = evaluate(results, _load_ground_truth())
    report["mode"] = detector.mode
    return jsonify(report)
