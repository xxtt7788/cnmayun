from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from app.config import settings
from app.normalization import ExtractedEventCandidate, extract_canonical_roles, infer_event_type_from_title, normalize_title_text


ALLOWED_EVENT_TYPES = {
    "appointment",
    "resignation",
    "removal",
    "reelection",
    "interim_assignment",
    "title_change",
    "nomination",
    "non_renewal",
    "retirement",
}


def ai_extraction_available() -> bool:
    return bool(settings.ai_extraction_enabled and settings.ai_api_base_url and settings.ai_api_key)


def _record_ai_usage(
    *,
    model: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    request_source: str | None = None,
    success: bool = True,
    error_message: str | None = None,
) -> None:
    """Record AI API usage to database (fire-and-forget)."""
    try:
        from app.db import SessionLocal
        from app.models import AIUsageLog
        db = SessionLocal()
        try:
            db.add(
                AIUsageLog(
                    model_name=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens or (prompt_tokens + completion_tokens),
                    request_source=request_source,
                    success=success,
                    error_message=error_message,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception:
        pass  # silently ignore logging failures


def _messages_url() -> str:
    base_url = settings.ai_api_base_url.rstrip("/")
    if base_url.endswith("/v1/messages"):
        return base_url
    return f"{base_url}/v1/messages"


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("AI 返回内容不是 JSON 对象")
    return json.loads(text[start : end + 1])


def _normalize_person_name(raw_name: Any) -> str | None:
    name = normalize_title_text(str(raw_name or ""))
    name = name.replace("先生", "").replace("女士", "").strip()
    if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", name):
        return name
    name = re.sub(r"\s+", " ", name)
    if re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{1,40}[A-Za-z]", name):
        return name
    return None


def _candidate_from_ai_payload(item: dict[str, Any]) -> ExtractedEventCandidate | None:
    person_name = _normalize_person_name(item.get("person_name"))
    if not person_name:
        return None

    role_raw = normalize_title_text(str(item.get("role_raw") or ""))
    role_canonical = str(item.get("role_canonical") or "").strip()
    if role_canonical not in extract_canonical_roles(role_raw):
        roles = extract_canonical_roles(f"{role_raw} {role_canonical}")
        role_canonical = roles[0] if roles else role_canonical
    if not role_canonical:
        return None

    event_type = str(item.get("event_type") or "").strip()
    if event_type not in ALLOWED_EVENT_TYPES:
        inferred = infer_event_type_from_title(str(item.get("evidence_excerpt") or ""))
        if not inferred:
            return None
        event_type = inferred

    excerpt = normalize_title_text(str(item.get("evidence_excerpt") or ""))[:180]
    if not excerpt or person_name not in excerpt:
        return None

    try:
        confidence = float(item.get("confidence", 0.86))
    except (TypeError, ValueError):
        confidence = 0.86
    confidence = min(max(confidence, 0.50), 0.93)
    return ExtractedEventCandidate(
        person_name=person_name,
        role_canonical=role_canonical,
        event_type=event_type,
        excerpt=excerpt,
        confidence=confidence,
    )


def extract_events_with_ai(title: str, body_text: str) -> list[ExtractedEventCandidate]:
    if not ai_extraction_available():
        return []

    normalized_title = normalize_title_text(title)
    normalized_body = normalize_title_text(body_text)[: settings.ai_text_char_limit]
    prompt = f"""
你是中国 A 股公告高管/董事变动抽取器。只抽取公告正文明确写出的真实人事变动，不要抽取列席会议、主持会议、审计委员会委员、提名委员会委员、担保/章程/利润分配等非人事事项。

允许角色 role_canonical：
- chairperson 董事长
- ceo_equivalent 总经理/总裁/CEO
- cfo_equivalent 财务负责人/财务总监/CFO
- board_secretary 董事会秘书/董秘
- senior_management 副总经理/副总裁/总法律顾问/首席合规官等高级管理人员
- director 董事/非独立董事/职工董事
- independent_director 独立董事

允许事件 event_type：
appointment, resignation, removal, reelection, interim_assignment, title_change, nomination, non_renewal, retirement

返回严格 JSON，不要解释：
{{"events":[{{"person_name":"张三","role_raw":"公司副总经理","role_canonical":"senior_management","event_type":"appointment","confidence":0.91,"evidence_excerpt":"董事会同意聘任张三先生担任公司副总经理"}}]}}

公告标题：{normalized_title}
公告正文：
{normalized_body}
""".strip()

    payload = {
        "model": settings.ai_model_name,
        "max_tokens": 1200,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    request = urllib.request.Request(
        _messages_url(),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": settings.ai_api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.ai_request_timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        _record_ai_usage(model=settings.ai_model_name, success=False, error_message=str(exc)[:500])
        return []

    # Record token usage
    usage = response_payload.get("usage") or {}
    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0
    total_tokens = usage.get("total_tokens") or (input_tokens + output_tokens)
    _record_ai_usage(
        model=settings.ai_model_name,
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        total_tokens=total_tokens,
        request_source=f"extract:{title[:80]}",
    )

    content = response_payload.get("content") or []
    text_parts = [part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text"]
    if not text_parts and isinstance(response_payload.get("text"), str):
        text_parts = [response_payload["text"]]
    if not text_parts:
        return []

    try:
        data = _extract_json_object("\n".join(text_parts))
    except (ValueError, json.JSONDecodeError):
        return []

    results: list[ExtractedEventCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    for item in data.get("events", []):
        if not isinstance(item, dict):
            continue
        candidate = _candidate_from_ai_payload(item)
        if not candidate:
            continue
        key = (candidate.person_name, candidate.role_canonical, candidate.event_type)
        if key in seen:
            continue
        seen.add(key)
        results.append(candidate)
    return results
