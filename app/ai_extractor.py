from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from app.config import settings
from app.normalization import (
    ExtractedEventCandidate,
    body_has_management_motion,
    extract_canonical_roles,
    extract_events_from_text,
    extract_person_name_from_title,
    infer_event_type_from_title,
    normalize_title_text,
    _normalize_person_name as _rule_normalize,
)

# In-memory cache: content_hash -> extraction results, avoids duplicate AI calls
_extraction_cache: dict[str, list[ExtractedEventCandidate]] = {}
_CACHE_MAX_SIZE = 500

# Optimization counters (in-memory, reset on restart)
_optimization_stats = {
    "cache_hits": 0,
    "smart_skips": 0,
    "prefilter_chars_saved": 0,
    "budget_rejections": 0,
    "no_signal_skips": 0,
    "paragraph_extraction_savings": 0,
}

# 403/429 cooldown: temporarily disable AI when API errors spike
_api_cooldown_until: float = 0.0

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

# Regex patterns for body text pre-filtering
_PREFILTER_PATTERNS = [
    re.compile(r"会议于.{5,30}召开.*?(?=。|$)", re.DOTALL),
    re.compile(r"应到董事\d+人.*?出席董事\d+人", re.DOTALL),
    re.compile(r"表决结果：.*?赞成\d+票.*?(?=。|$)", re.DOTALL),
    re.compile(r"（\d+票同意.*?\d+票反对.*?\d+票弃权）", re.DOTALL),
    re.compile(r"本次会议的召集.*?符合.*?公司法.*?章程.*?规定"),
    re.compile(r"独立意见.{0,5}：.*?同意", re.DOTALL),
    re.compile(r"特此公告\.?"),
    re.compile(r"备查文件：.*", re.DOTALL),
    re.compile(r"证券代码：\d{6}\s*证券简称：\S+\s*公告编号：\S+"),
    re.compile(r"本公司及董事会全体成员保证信息披露的内容真实、准确、完整.*?重大遗漏", re.DOTALL),
    re.compile(r"根据《.*?》.*?的有关规定", re.DOTALL),
    re.compile(r"以上议案.*?审议通过", re.DOTALL),
    re.compile(r"附件[:：].*", re.DOTALL),
]

# Personnel keywords for paragraph extraction
_PERSONNEL_KEYWORDS = re.compile(r"聘任|任命|选举|选聘|当选|提名|辞职|辞任|辞去|免去|免职|解聘|不再担任|代行|补选|换届|退休|离任")

# Minimal system prompt (~90 tokens) — removed evidence_excerpt from output schema
_SYSTEM_PROMPT = """从A股公告提取人事变动。忽略列席/委员会/担保/章程/分红等。
角色:chairperson|ceo_equivalent|cfo_equivalent|board_secretary|senior_management|director|independent_director
事件:appointment|resignation|removal|reelection|interim_assignment|title_change|nomination|non_renewal|retirement
返:{"events":[{"p":"名","r":"原职","c":"角色","e":"事件","x":"原文片段"}]}"""

_USER_TEMPLATE = "{title}\n{body}"


def ai_extraction_available() -> bool:
    if _api_cooldown_until > time.time():
        return False
    return bool(settings.ai_extraction_enabled and settings.ai_api_base_url and settings.ai_api_key)


def get_optimization_stats() -> dict:
    return dict(_optimization_stats)


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
        pass


def _messages_url() -> str:
    base_url = settings.ai_api_base_url.rstrip("/")
    if base_url.endswith("/v1/messages"):
        return base_url
    return f"{base_url}/v1/messages"


def _prefilter_body(text: str) -> str:
    original_len = len(text)
    for pattern in _PREFILTER_PATTERNS:
        text = pattern.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    saved = original_len - len(text)
    if saved > 0:
        _optimization_stats["prefilter_chars_saved"] += saved
    return text


def _extract_relevant_paragraphs(text: str, max_chars: int) -> str:
    """Extract only paragraphs containing personnel keywords + 1 context paragraph."""
    paragraphs = re.split(r"\n+|[。；;]", text)
    paragraphs = [p.strip() for p in paragraphs if len(p.strip()) > 15]

    matched_indices = set()
    for i, p in enumerate(paragraphs):
        if _PERSONNEL_KEYWORDS.search(p):
            matched_indices.add(i)
            if i > 0:
                matched_indices.add(i - 1)
            if i + 1 < len(paragraphs):
                matched_indices.add(i + 1)

    if not matched_indices:
        return text[:max_chars]

    result = []
    total_len = 0
    for i in sorted(matched_indices):
        para = paragraphs[i] + "。"
        if total_len + len(para) > max_chars:
            break
        result.append(para)
        total_len += len(para)

    if not result:
        return text[:max_chars]

    original_len = len(text)
    saved = original_len - total_len
    if saved > 0:
        _optimization_stats["paragraph_extraction_savings"] += saved
    return "".join(result)


def _check_token_budget() -> bool:
    if settings.ai_daily_token_budget <= 0 and settings.ai_hourly_token_budget <= 0:
        return True
    try:
        from datetime import datetime
        from sqlalchemy import func, select
        from app.db import SessionLocal
        from app.models import AIUsageLog
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            if settings.ai_hourly_token_budget > 0:
                hour_start = now.replace(minute=0, second=0, microsecond=0)
                hourly_tokens = db.scalar(
                    select(func.coalesce(func.sum(AIUsageLog.total_tokens), 0)).where(
                        AIUsageLog.success == True, AIUsageLog.created_at >= hour_start
                    )
                ) or 0
                if int(hourly_tokens) >= settings.ai_hourly_token_budget:
                    _optimization_stats["budget_rejections"] += 1
                    return False
            if settings.ai_daily_token_budget > 0:
                day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                daily_tokens = db.scalar(
                    select(func.coalesce(func.sum(AIUsageLog.total_tokens), 0)).where(
                        AIUsageLog.success == True, AIUsageLog.created_at >= day_start
                    )
                ) or 0
                if int(daily_tokens) >= settings.ai_daily_token_budget:
                    _optimization_stats["budget_rejections"] += 1
                    return False
        finally:
            db.close()
    except Exception:
        pass
    return True


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
    """委托 app.normalization._normalize_person_name — 统一两路径的人名校验。

    包含前缀剥离（"经"、"经审查"、"经审核"、"经董事会"、"提名"、"聘任"等）、
    INVALID_PERSON_TOKENS 检查、"经理/董事/委员" 后缀检查、
    "声明/名单/议案/报告" 检查、拉丁名 fallback。
    """
    return _rule_normalize(str(raw_name or ""))


def _candidate_from_ai_payload(item: dict[str, Any]) -> ExtractedEventCandidate | None:
    # Support both short keys (p,r,c,e,x) and long keys (person_name, etc.) for backward compat
    person_name = _normalize_person_name(item.get("p") or item.get("person_name"))
    if not person_name:
        return None

    role_raw = normalize_title_text(str(item.get("r") or item.get("role_raw") or ""))
    role_canonical = str(item.get("c") or item.get("role_canonical") or "").strip()
    if role_canonical not in extract_canonical_roles(role_raw):
        roles = extract_canonical_roles(f"{role_raw} {role_canonical}")
        role_canonical = roles[0] if roles else role_canonical
    if not role_canonical:
        return None

    event_type = str(item.get("e") or item.get("event_type") or "").strip()
    if event_type not in ALLOWED_EVENT_TYPES:
        excerpt_text = str(item.get("x") or item.get("evidence_excerpt") or "")
        inferred = infer_event_type_from_title(excerpt_text)
        if not inferred:
            return None
        event_type = inferred

    excerpt = normalize_title_text(str(item.get("x") or item.get("evidence_excerpt") or ""))[:180]
    if not excerpt or person_name not in excerpt:
        return None

    return ExtractedEventCandidate(
        person_name=person_name,
        role_canonical=role_canonical,
        event_type=event_type,
        excerpt=excerpt,
        confidence=0.86,
    )


def _content_hash(title: str, body: str) -> str:
    return hashlib.md5(f"{title}\n{body}".encode()).hexdigest()


def _check_cache(content_hash: str) -> list[ExtractedEventCandidate] | None:
    return _extraction_cache.get(content_hash)


def _store_cache(content_hash: str, results: list[ExtractedEventCandidate]) -> None:
    if len(_extraction_cache) >= _CACHE_MAX_SIZE:
        oldest_key = next(iter(_extraction_cache))
        del _extraction_cache[oldest_key]
    _extraction_cache[content_hash] = results


def extract_events_with_ai(
    title: str,
    body_text: str,
    *,
    rule_confidence: float | None = None,
    rule_candidate_count: int = 0,
) -> list[ExtractedEventCandidate]:
    """Extract events using AI. Only called when rules can't handle it."""
    if not ai_extraction_available():
        return []

    # Skip 1: rule engine already found candidates with good confidence
    if rule_confidence is not None and rule_confidence >= 0.85:
        _optimization_stats["smart_skips"] += 1
        return []

    # Skip 2: no management motion signal at all — AI would return empty
    normalized_title = normalize_title_text(title)
    title_event_type = infer_event_type_from_title(normalized_title)
    title_person_name = extract_person_name_from_title(normalized_title)
    has_body_signal = body_has_management_motion(body_text)
    if not title_event_type and not title_person_name and not has_body_signal:
        _optimization_stats["no_signal_skips"] += 1
        return []

    # Skip 3: title alone gives full event info (person + role + event type)
    # and body confirms it — rules likely already covered, or AI won't add value
    if title_person_name and title_event_type and rule_candidate_count > 0:
        _optimization_stats["smart_skips"] += 1
        return []

    # Check token budget
    if not _check_token_budget():
        return []

    normalized_body = _prefilter_body(normalize_title_text(body_text))
    normalized_body = _extract_relevant_paragraphs(normalized_body, settings.ai_text_char_limit)

    # Adaptive char limit: if title already has person+event, body only needs short context
    if title_person_name and title_event_type:
        normalized_body = normalized_body[:2000]

    # Check cache
    cache_key = _content_hash(normalized_title, normalized_body)
    cached = _check_cache(cache_key)
    if cached is not None:
        _optimization_stats["cache_hits"] += 1
        return cached

    payload = {
        "model": settings.ai_model_name,
        "max_tokens": 200,
        "temperature": 0,
        "system": _SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": _USER_TEMPLATE.format(title=normalized_title, body=normalized_body)}],
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

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=settings.ai_request_timeout) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < max_retries:
                time.sleep((2 ** attempt) + 0.5)
                continue
            if exc.code == 403:
                _api_cooldown_until = time.time() + 3600
                _record_ai_usage(model=settings.ai_model_name, success=False, error_message="HTTP 403: cooldown 1h")
                return []
            _record_ai_usage(model=settings.ai_model_name, success=False, error_message=str(exc)[:500])
            return []
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

    _store_cache(cache_key, results)
    return results