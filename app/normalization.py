from __future__ import annotations

import re
from dataclasses import dataclass


ROLE_LABELS = {
    "chairperson": "董事长",
    "ceo_equivalent": "总经理/总裁",
    "cfo_equivalent": "财务负责人/CFO",
    "board_secretary": "董事会秘书/董秘",
    "senior_management": "高级管理人员/副总经理",
    "director": "董事",
    "independent_director": "独立董事",
}

EVENT_TYPE_LABELS = {
    "appointment": "任命",
    "resignation": "辞职",
    "removal": "免职",
    "reelection": "换届连任",
    "interim_assignment": "代行职责",
    "title_change": "职务调整",
    "nomination": "提名",
    "non_renewal": "未续任",
    "retirement": "退休离任",
}

ROLE_PRIORITY = {
    "chairperson": 10,
    "ceo_equivalent": 20,
    "cfo_equivalent": 30,
    "board_secretary": 35,
    "senior_management": 38,
    "independent_director": 40,
    "director": 50,
}

CORE_ROLE_SET = {
    "chairperson",
    "ceo_equivalent",
    "cfo_equivalent",
    "board_secretary",
    "senior_management",
    "director",
    "independent_director",
}

MANAGEMENT_TITLE_KEYWORDS = (
    "董事长",
    "总经理",
    "总裁",
    "首席执行官",
    "CEO",
    "财务负责人",
    "财务总监",
    "首席财务官",
    "CFO",
    "副总经理",
    "副总裁",
    "董事会秘书",
    "董秘",
    "董事",
    "独立董事",
)

ACTION_KEYWORDS = ("聘任", "任命", "选举", "当选", "提名", "辞职", "辞任", "辞去", "免去", "免职", "解聘", "换届", "补选", "代行", "调整", "变更", "不再担任", "退休")

FALSE_POSITIVE_KEYWORDS = (
    "限制性股票",
    "股票期权",
    "激励计划",
    "激励对象",
    "员工持股计划",
    "核查意见",
    "公示情况说明",
    "募集资金",
    "关联交易",
    "对外担保",
    "财务资助",
    "定期报告",
    "年度报告",
    "季度报告",
    "半年度报告",
)
NON_PERSONNEL_SENTENCE_KEYWORDS = (
    "会计师事务所",
    "审计机构",
    "审计工作",
)

INVALID_PERSON_TOKENS = ("第", "届", "董事会", "监事会", "委员会", "公司", "议案", "公告", "候选人", "专门会议")
LATIN_PERSON_PATTERN = r"[A-Za-z][A-Za-z .'\-]{1,40}[A-Za-z]"

PERSON_PATTERNS = (
    r"关于(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士).*?(辞职|辞任|辞去|聘任|任命|当选|被提名)",
    r"(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士).*?(辞职|辞任|辞去|聘任|任命|当选|被提名)",
    r"提名(?P<name>[\u4e00-\u9fa5]{2,4})为",
    r"聘任(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士)?为",
    r"选举(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士)?为",
)

ROLE_DIRECT_PATTERNS = (
    (r"(?<!非)独立董事", "independent_director"),
    (r"董事长", "chairperson"),
    (r"(总经理|总裁|首席执行官|CEO)", "ceo_equivalent"),
    (r"(财务负责人|财务总监|首席财务官|CFO)", "cfo_equivalent"),
    (r"(董事会秘书|董秘)", "board_secretary"),
    (r"(副总经理|常务副总经理|高级副总裁|副总裁|总法律顾问|首席合规官|首席技术官|首席运营官)", "senior_management"),
)

EVENT_PATTERNS: tuple[tuple[str, str, float], ...] = (
    (
        "interim_assignment",
        r"(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士)?(?:暂时)?代行(?P<role>[^，,。.;；\n]{0,24})职责",
        0.95,
    ),
    (
        "resignation",
        r"(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士)?(?:因[^，,。.;；\n]{0,20})?(?:申请)?辞去(?P<role>[^，,。.;；\n]{0,24})职务",
        0.96,
    ),
    (
        "removal",
        r"(?:免去|免职|解聘)(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士)?(?P<role>[^，,。.;；\n]{0,24})职务",
        0.96,
    ),
    (
        "appointment",
        r"(?:聘任|任命|选举(?!产生)|选聘|补选|当选)(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士)?(?:（[^）]{0,30}）|\([^)]{0,30}\))?\s*为(?P<role>[^，,。.;；\n]{0,24})",
        0.95,
    ),
    (
        "appointment",
        r"(?:公司)?(?:同意)?聘任(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士)?(?:（[^）]{0,30}）|\([^)]{0,30}\))?\s*担任(?P<role>[^，,。.;；\n]{0,24})",
        0.95,
    ),
    (
        "appointment",
        r"(?:聘任|任命|选举(?!产生)|选聘|补选|当选)(?:公司)?(?P<role_before>[^，,。.;；\n]{0,32}?)(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士)?(?:（[^）]{0,30}）|\([^)]{0,30}\))?\s*(?:担任|为)(?:公司)?(?P<role_after>[^，,。.;；\n]{0,32})",
        0.96,
    ),
    (
        "appointment",
        r"关于(?:聘任|任命|选举|选聘|补选)(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士)?(?:（[^）]{0,30}）|\([^)]{0,30}\))?\s*为(?:公司)?(?P<role>[^，,。.;；\n]{0,24})的议案",
        0.96,
    ),
    (
        "nomination",
        r"(?:提名(?!委员会)|被提名为)(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士)?(?:（[^）]{0,30}）|\([^)]{0,30}\))?\s*为?(?P<role>[^，,。.;；\n]{0,24}(?:董事|独立董事)(?:候选人)?)",
        0.93,
    ),
    (
        "reelection",
        r"(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士)?连任(?P<role>[^，,。.;；\n]{0,24})",
        0.94,
    ),
    (
        "non_renewal",
        r"(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士)?(?:任期届满)?不再担任(?P<role>[^，,。.;；\n]{0,24})",
        0.93,
    ),
    (
        "retirement",
        r"(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士)?因退休辞去(?P<role>[^，,。.;；\n]{0,24})职务",
        0.96,
    ),
)


@dataclass(slots=True)
class ExtractedEventCandidate:
    person_name: str
    role_canonical: str
    event_type: str
    excerpt: str
    confidence: float


@dataclass(slots=True)
class ReviewExtractionHint:
    person_name: str | None
    role_canonical: str | None
    role_raw: str | None
    event_type: str | None
    excerpt: str
    confidence: float
    source: str
    missing_fields: tuple[str, ...]


def role_label(value: str) -> str:
    return ROLE_LABELS.get(value, value)


def event_type_label(value: str) -> str:
    return EVENT_TYPE_LABELS.get(value, value)


def role_priority(value: str) -> int:
    return ROLE_PRIORITY.get(value, 999)


def is_core_role(value: str) -> bool:
    return value in CORE_ROLE_SET


def normalize_title_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    replacements = {
        "\u3000": " ",
        "\xa0": " ",
        "\r": "\n",
        "（": "(",
        "）": ")",
        "：": ":",
        "；": ";",
        "，": ",",
        "。": ".",
        "、": ",",
    }
    normalized = raw_text
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{2,}", "\n", normalized)
    return normalized.strip()


def _contains_false_positive_keyword(text: str) -> bool:
    normalized = normalize_title_text(text)
    return any(keyword in normalized for keyword in FALSE_POSITIVE_KEYWORDS)


def _director_role_match(text: str) -> bool:
    explicit_patterns = (
        r"董事候选人",
        r"补选董事",
        r"执行董事",
        r"职工董事",
        r"非独立董事",
        r"董事职务",
        r"担任董事",
        r"辞去董事",
        r"不再担任董事",
        r"被提名为董事",
        r"选举[^，,。.;；\\n]{0,10}为董事(?!长)",
    )
    return any(re.search(pattern, text) for pattern in explicit_patterns)


def extract_canonical_roles(raw_text: str) -> list[str]:
    normalized = normalize_title_text(raw_text)
    if not normalized:
        return []

    lowered = normalized.lower()
    roles: list[str] = []
    for pattern, role in ROLE_DIRECT_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            if role == "chairperson" and re.search(r"副董事长", normalized):
                continue
            if role == "ceo_equivalent" and re.search(r"(副总经理|常务副总经理|联席总裁|副总裁)", normalized, re.IGNORECASE):
                continue
            roles.append(role)

    if _director_role_match(normalized):
        roles.append("director")

    if "ceo" in lowered and "vice ceo" not in lowered and "ceo_equivalent" not in roles:
        roles.append("ceo_equivalent")
    if "cfo" in lowered and "cfo_equivalent" not in roles:
        roles.append("cfo_equivalent")

    deduped: list[str] = []
    for item in roles:
        if item not in deduped:
            deduped.append(item)
    if "independent_director" in deduped and "director" in deduped and "非独立董事" not in normalized:
        deduped = [item for item in deduped if item != "director"]
    if "非独立董事" in normalized and "director" not in deduped:
        deduped.append("director")
    return deduped


def infer_event_type_from_title(title: str) -> str | None:
    normalized = normalize_title_text(title)
    if not normalized:
        return None
    if "代行" in normalized or "代为履行" in normalized:
        return "interim_assignment"
    if "换届" in normalized or "连任" in normalized:
        return "reelection"
    if "提名" in normalized or "候选人" in normalized:
        return "nomination"
    if any(token in normalized for token in ("聘任", "聘请", "任命", "选举", "补选", "当选")):
        return "appointment"
    if any(token in normalized for token in ("辞职", "辞任", "辞去")):
        return "resignation"
    if any(token in normalized for token in ("免去", "免职", "解聘")):
        return "removal"
    if "退休" in normalized:
        return "retirement"
    if "不再担任" in normalized or "未续任" in normalized:
        return "non_renewal"
    if "调整" in normalized or "变更" in normalized:
        return "title_change"
    return None


def is_management_notice(title: str) -> bool:
    normalized = normalize_title_text(title)
    if not normalized or _contains_false_positive_keyword(normalized):
        return False
    if any(keyword in normalized for keyword in MANAGEMENT_TITLE_KEYWORDS) and any(token in normalized for token in ACTION_KEYWORDS):
        return True
    return "董事会" in normalized and "决议" in normalized


def extract_person_name_from_title(title: str) -> str | None:
    normalized = normalize_title_text(title)
    for pattern in PERSON_PATTERNS:
        match = re.search(pattern, normalized)
        if match:
            return match.group("name")
    return None


def body_has_management_motion(text: str) -> bool:
    normalized = normalize_title_text(text)
    if not normalized or _contains_false_positive_keyword(normalized):
        return False
    sentence_pattern = re.compile(r"[^。；;\n]{0,180}(?:聘任|任命|选举|选聘|当选|提名|辞职|辞任|辞去|免去|免职|解聘|不再担任|代行|补选)[^。；;\n]{0,180}")
    return any(_sentence_has_actionable_management_event(match.group(0)) for match in sentence_pattern.finditer(normalized))


def should_skip_notice(title: str, body_text: str) -> bool:
    title_normalized = normalize_title_text(title)
    body_normalized = normalize_title_text(body_text)
    if _contains_false_positive_keyword(title_normalized):
        return True
    return _contains_false_positive_keyword(body_normalized) and not body_has_management_motion(body_normalized)


def _normalize_person_name(raw_name: str) -> str | None:
    normalized = normalize_title_text(raw_name).replace("先生", "").replace("女士", "").strip()
    normalized = re.sub(r"^(?:同意|拟|经审查|经审核|经董事会|被提名为|被提名|提名|补选|聘任|任命|选举|选聘|当选|免去|免职|解聘)+", "", normalized).strip()
    while len(normalized) >= 3 and normalized[0] in {"任", "聘", "选", "举", "命", "补", "提"}:
        normalized = normalized[1:]
    normalized = re.sub(r"[先女男已]+$", "", normalized).strip()
    if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", normalized):
        if any(token in normalized for token in INVALID_PERSON_TOKENS):
            return None
        if any(token in normalized for token in ("经理", "董事", "委员", "主席", "主持", "列席")):
            return None
        if any(token in normalized for token in ("声明", "名单", "议案", "报告")):
            return None
        return normalized
    normalized = re.sub(r"\s+", " ", normalized)
    if not re.fullmatch(LATIN_PERSON_PATTERN, normalized):
        return None
    if any(token in normalized for token in INVALID_PERSON_TOKENS):
        return None
    return normalized


def _clean_excerpt(raw_excerpt: str) -> str:
    excerpt = normalize_title_text(raw_excerpt)
    excerpt = re.sub(r"\s+", " ", excerpt)
    return excerpt[:180]


def _is_procedural_sentence(text: str) -> bool:
    normalized = normalize_title_text(text)
    procedural_tokens = (
        "列席",
        "主持",
        "召集",
        "回避表决",
        "授权公司经营管理层",
        "授权公司管理层",
        "独立董事专门会议",
        "审计委员会委员",
        "提名委员会委员",
        "薪酬与考核委员会委员",
        "战略委员会委员",
        "委员会召集人",
        "主任委员",
    )
    if any(token in normalized for token in procedural_tokens):
        action_text = normalized
        for token in ("提名委员会", "审计委员会", "薪酬与考核委员会", "战略委员会", "独立董事专门会议"):
            action_text = action_text.replace(token, "")
        core_tokens = ("聘任", "任命", "选举", "补选", "提名", "辞职", "辞去", "不再担任", "担任公司")
        if not any(token in action_text for token in core_tokens):
            return True
    return False


def _sentence_has_actionable_management_event(text: str) -> bool:
    normalized = normalize_title_text(text)
    if not normalized or _is_procedural_sentence(normalized):
        return False
    if any(token in normalized for token in NON_PERSONNEL_SENTENCE_KEYWORDS):
        return False
    if not any(token in normalized for token in ACTION_KEYWORDS):
        return False
    if "委员会委员" in normalized and not any(token in normalized for token in ("非独立董事", "独立董事候选人", "董事候选人", "副总经理", "总经理", "财务总监", "董事会秘书", "董秘")):
        return False
    return bool(extract_canonical_roles(normalized)) or "高级管理人员任职资格" in normalized


def _split_person_names(raw_names: str) -> list[str]:
    cleaned = normalize_title_text(raw_names)
    cleaned = re.sub(r"^(同意|拟|公司|董事会|经|审查|审核|提名委员会|认为|提名)+", "", cleaned).strip()
    cleaned = re.sub(r"(同意|拟|公司|董事会|经|审查|审核|提名委员会|认为|第[一二三四五六七八九十\d]+届)$", "", cleaned)
    cleaned = re.sub(r"\s*(?:及|和|与)\s*", "|", cleaned)
    cleaned = re.sub(r"\s*[,，、]\s*", "|", cleaned)
    cleaned = re.sub(r"\n+", "|", cleaned)
    parts = [segment.strip() for segment in cleaned.split("|")]
    names: list[str] = []
    for part in parts:
        name = _normalize_person_name(part)
        if name and name not in names:
            names.append(name)
    return names


def _extract_hint_person_names(sentence: str) -> list[str | None]:
    action_patterns = (
        r"(?:聘任|任命|选举|选聘|补选|当选|提名|被提名为)(?P<name>[\u4e00-\u9fa5]{2,4})(先生|女士)",
        r"(?P<name>[\u4e00-\u9fa5]{2,4}|[A-Za-z][A-Za-z .'\-]{1,40}[A-Za-z])(?:先生|女士)?(?:\([^)]{0,30}\))?\s*(?:担任|为)(?:公司)?",
    )
    names: list[str] = []
    for pattern in action_patterns:
        for match in re.finditer(pattern, sentence):
            normalized_name = _normalize_person_name(match.group("name"))
            if normalized_name and normalized_name not in names:
                names.append(normalized_name)
    if names:
        return names
    title_name = extract_person_name_from_title(sentence)
    return [title_name] if title_name else [None]


def extract_events_from_text(title: str, body_text: str) -> list[ExtractedEventCandidate]:
    normalized_title = normalize_title_text(title)
    normalized_body = normalize_title_text(body_text)
    search_text = f"{normalized_title}\n{normalized_body}".strip()
    if not search_text or should_skip_notice(normalized_title, normalized_body):
        return []

    results: list[ExtractedEventCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    for event_type, pattern, base_confidence in EVENT_PATTERNS:
        for match in re.finditer(pattern, search_text):
            person_name = _normalize_person_name(match.group("name"))
            if not person_name:
                continue
            groups = match.groupdict()
            role_text = " ".join(
                value
                for key, value in groups.items()
                if key.startswith("role") and value
            ) or groups.get("role", "") or match.group(0)
            roles = extract_canonical_roles(role_text)
            if not roles:
                continue
            excerpt = _clean_excerpt(match.group(0))
            if any(token in excerpt for token in ("提名人声明", "候选人声明", "声明》")):
                continue
            for role_canonical in roles:
                key = (person_name, role_canonical, event_type)
                if key in seen:
                    continue
                seen.add(key)
                confidence = base_confidence + (0.01 if normalized_body else 0.0)
                results.append(
                    ExtractedEventCandidate(
                        person_name=person_name,
                        role_canonical=role_canonical,
                        event_type=event_type,
                        excerpt=excerpt,
                        confidence=min(confidence, 0.99),
                    )
                )

    list_patterns = (
        (
            "nomination",
            r"(?:同意)?提名(?!委员会)(?P<names>[\u4e00-\u9fa5A-Za-z .'\-、,，\s]{2,120}?)为(?P<role>[^，,。.;；\n]{0,32}?(?:非独立董事候选人|独立董事候选人|董事候选人))(?=[，,。.;；\n]|$)",
            0.92,
        ),
        (
            "appointment",
            r"(?:同意)?(?:补选|选举(?!产生)|聘任|任命)(?P<names>[\u4e00-\u9fa5A-Za-z .'\-、,，\s]{2,120}?)为(?P<role>[^，,。.;；\n]{0,32}?(?:非独立董事|独立董事|董事|副总经理|财务总监|总经理|董事会秘书|董秘)(?:候选人)?)(?=[，,。.;；\n]|$)",
            0.94,
        ),
    )
    for event_type, pattern, base_confidence in list_patterns:
        for match in re.finditer(pattern, search_text):
            if _is_procedural_sentence(match.group(0)):
                continue
            roles = extract_canonical_roles(match.group("role"))
            if not roles:
                continue
            excerpt = _clean_excerpt(match.group(0))
            for person_name in _split_person_names(match.group("names")):
                for role_canonical in roles:
                    key = (person_name, role_canonical, event_type)
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(
                        ExtractedEventCandidate(
                            person_name=person_name,
                            role_canonical=role_canonical,
                            event_type=event_type,
                            excerpt=excerpt,
                            confidence=min(base_confidence + (0.01 if normalized_body else 0.0), 0.99),
                        )
                    )

    return results


def extract_review_hints_from_text(title: str, body_text: str, limit: int = 8) -> list[ReviewExtractionHint]:
    normalized_title = normalize_title_text(title)
    normalized_body = normalize_title_text(body_text)
    search_text = f"{normalized_title}\n{normalized_body}".strip()
    if not search_text:
        return []

    hints: list[ReviewExtractionHint] = []
    seen: set[tuple[str | None, str | None, str | None, str]] = set()

    for candidate in extract_events_from_text(title, body_text):
        key = (candidate.person_name, candidate.role_canonical, candidate.event_type, candidate.excerpt)
        if key in seen:
            continue
        seen.add(key)
        hints.append(
            ReviewExtractionHint(
                person_name=candidate.person_name,
                role_canonical=candidate.role_canonical,
                role_raw=role_label(candidate.role_canonical),
                event_type=candidate.event_type,
                excerpt=candidate.excerpt,
                confidence=candidate.confidence,
                source="规则可落地事件",
                missing_fields=(),
            )
        )

    sentence_pattern = re.compile(r"[^。；;\n]{0,180}(?:聘任|任命|选举|选聘|当选|提名|辞职|辞任|辞去|免去|免职|解聘|不再担任|代行|补选)[^。；;\n]{0,180}")
    for match in sentence_pattern.finditer(search_text):
        sentence = _clean_excerpt(match.group(0))
        if (
            not sentence
            or _contains_false_positive_keyword(sentence)
            or _is_procedural_sentence(sentence)
            or any(token in sentence for token in NON_PERSONNEL_SENTENCE_KEYWORDS)
        ):
            continue
        if extract_events_from_text("", sentence):
            continue

        person_names = _extract_hint_person_names(sentence)
        # 过滤：句子含人事关键词但无具体人名（如"审议通过了《关于提名...的议案》"），
        # 跳过该句，不生成低信号 hint。
        if not any(person_names):
            continue

        roles = extract_canonical_roles(sentence)
        event_type = infer_event_type_from_title(sentence)
        if ("提名委员会" in sentence or "提名委员" in sentence) and event_type == "nomination" and not roles:
            continue
        role_values: list[str | None] = roles or [None]
        for person_name in person_names:
            for role_canonical in role_values:
                missing = []
                if not person_name:
                    missing.append("人员姓名")
                if not role_canonical:
                    missing.append("角色职位")
                if not event_type:
                    missing.append("事件类型")
                key = (person_name, role_canonical, event_type, sentence)
                if key in seen:
                    continue
                seen.add(key)
                hints.append(
                    ReviewExtractionHint(
                        person_name=person_name,
                        role_canonical=role_canonical,
                        role_raw=role_label(role_canonical) if role_canonical else None,
                        event_type=event_type,
                        excerpt=sentence,
                        confidence=0.78 if not missing else 0.55,
                        source="正文线索",
                        missing_fields=tuple(missing),
                    )
                )
                if len(hints) >= limit:
                    return hints

    return hints[:limit]


# --- Bot detection (shared between middleware write-path and stats read-path) ---
# Substring match (lowercased). Core search engine crawlers (Googlebot, Bingbot,
# Baiduspider, Sogou) are intentionally NOT listed to preserve SEO.
_BOT_SIGNATURES: tuple[str, ...] = (
    "gptbot",                # OpenAI: trains GPT models, no SEO value
    "mj12bot",               # Majestic SEO: link index scraper
    "googleother",           # Google non-search crawler
    "tlm-audit-scanner",     # Unknown scanner
    "ahrefsbot",             # Ahrefs SEO tool
    "semrushbot",            # SEMrush SEO tool
    "dotbot",                # Moz SEO tool
    "yandexbot",             # Yandex (low traffic value for China B2B)
    "exabot",                # Exalead (defunct search engine)
    "facebot",               # Facebook scraper
    "ia_archiver",           # Internet Archive
    "datadog",               # Datadog monitoring crawler
    "uptimerobot",           # Uptime monitoring
    "screaming frog",        # SEO audit tool
)


def is_bot_user_agent(user_agent: str | None) -> bool:
    """Return True if the User-Agent is a known data-scraping bot.

    Single source of truth — reused by the request middleware (write path) and
    the stats aggregator / get_stats (read path). Centralising the signature list
    avoids the bug of two divergent bot lists drifting apart.
    """
    if not user_agent:
        return True
    ua_lower = user_agent.lower()
    return any(sig in ua_lower for sig in _BOT_SIGNATURES)
