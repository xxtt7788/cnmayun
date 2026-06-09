from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings


PROJECT_MEMORY_VERSION = "2026-04-18"

PROJECT_MEMORY_PAYLOAD: dict[str, Any] = {
    "version": PROJECT_MEMORY_VERSION,
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "project_name": "中国上市公司高管与董事变动追踪",
    "core_definition": "一个面向中国A股市场的高管与董事变动情报系统，把分散公告和当前领导层基线转成可监控、可检索、可导出、可提醒的结构化数据产品。",
    "phase_one_product_name": "上市公司高管人事动态",
    "primary_users": [
        "猎头顾问",
        "董事会搜寻顾问",
        "高端人才咨询团队",
    ],
    "core_workflow": [
        "发现高价值高管变动",
        "查看公司当前领导层上下文",
        "查看人物历史任职轨迹",
        "导出候选名单",
        "持续关注与提醒",
    ],
    "product_focus": [
        "董事长",
        "CEO等价角色",
        "CFO等价角色",
    ],
    "non_goals": [
        "不做散户资讯站",
        "不做大而全金融终端",
        "不在第一阶段主打复杂关系图",
        "不同时扩张到港股和美股中概",
    ],
    "source_of_truth": "docs/PROJECT_MASTER_PLAN.md",
}


def ensure_project_memory() -> Path:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    memory_path = settings.project_memory_path
    existing: dict[str, Any] | None = None
    if memory_path.exists():
        try:
            existing = json.loads(memory_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = None
    payload = dict(PROJECT_MEMORY_PAYLOAD)
    if existing and existing.get("version") == PROJECT_MEMORY_VERSION:
        payload["updated_at"] = existing.get("updated_at", payload["updated_at"])
    memory_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return memory_path


def load_project_memory() -> dict[str, Any]:
    ensure_project_memory()
    return json.loads(settings.project_memory_path.read_text(encoding="utf-8"))
