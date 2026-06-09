from __future__ import annotations

import http.client
import json
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import settings
from app.normalization import is_management_notice


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)

EASTMONEY_SUGGEST_URL = "https://searchapi.eastmoney.com/api/suggest/get"
EASTMONEY_SUGGEST_TOKEN = "D43BF722C8E33BDC906FB84D85E326E8"


@dataclass(slots=True)
class StockListEntry:
    code: str
    short_name: str
    org_id: str
    category: str


@dataclass(slots=True)
class AnnouncementEntry:
    announcement_id: str
    sec_code: str
    sec_name: str
    org_id: str | None
    title: str
    announcement_date: date
    adjunct_url: str
    source_url: str
    column_id: str | None
    announcement_type: str | None


def _request_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    full_url = f"{url}?{urlencode(params)}" if params else url
    last_error: Exception | None = None
    retries = max(settings.cninfo_request_retries, 1)
    for attempt in range(1, retries + 1):
        request = Request(
            full_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json,text/plain,*/*",
                "Referer": "https://www.cninfo.com.cn/",
            },
        )
        try:
            with urlopen(request, timeout=settings.cninfo_request_timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code not in {408, 429}:
                raise
            last_error = exc
        except (URLError, TimeoutError, OSError, ConnectionError, json.JSONDecodeError, http.client.IncompleteRead) as exc:
            last_error = exc

        if attempt < retries:
            time.sleep(settings.cninfo_retry_backoff_seconds * attempt)

    assert last_error is not None
    raise last_error


def _post_json(url: str, body: dict[str, Any]) -> dict[str, Any]:
    last_error: Exception | None = None
    retries = max(settings.cninfo_request_retries, 1)
    encoded = urlencode(body).encode("utf-8")
    for attempt in range(1, retries + 1):
        request = Request(
            url,
            data=encoded,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json,text/plain,*/*",
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
            },
        )
        try:
            with urlopen(request, timeout=settings.cninfo_request_timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code not in {408, 429}:
                raise
            last_error = exc
        except (URLError, TimeoutError, OSError, ConnectionError, json.JSONDecodeError, http.client.IncompleteRead) as exc:
            last_error = exc

        if attempt < retries:
            time.sleep(settings.cninfo_retry_backoff_seconds * attempt)

    assert last_error is not None
    raise last_error


def fetch_binary(url: str) -> bytes:
    last_error: Exception | None = None
    retries = max(settings.cninfo_request_retries, 1)
    for attempt in range(1, retries + 1):
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/pdf,application/octet-stream,*/*",
                "Referer": "https://www.cninfo.com.cn/",
            },
        )
        try:
            with urlopen(request, timeout=settings.cninfo_request_timeout) as response:
                return response.read()
        except HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code not in {408, 429}:
                raise
            last_error = exc
        except (URLError, TimeoutError, OSError, ConnectionError, http.client.IncompleteRead) as exc:
            last_error = exc

        if attempt < retries:
            time.sleep(settings.cninfo_retry_backoff_seconds * attempt)

    assert last_error is not None
    raise last_error


def fetch_stock_universe() -> list[StockListEntry]:
    payload = _request_json(settings.cninfo_stock_list_url)
    rows = payload.get("stockList", [])
    items: list[StockListEntry] = []
    for row in rows:
        code = str(row.get("code", "")).strip()
        short_name = str(row.get("zwjc", "")).strip()
        org_id = str(row.get("orgId", "")).strip()
        category = str(row.get("category", "")).strip()
        if not code or not short_name or not org_id:
            continue
        if "A股" not in category:
            continue
        items.append(StockListEntry(code=code, short_name=short_name, org_id=org_id, category=category))
    return items


def fetch_company_introduction(ticker: str) -> dict[str, Any]:
    return _request_json(settings.cninfo_company_intro_url, {"scode": ticker})


def fetch_company_executives(ticker: str) -> dict[str, Any]:
    return _request_json(settings.cninfo_company_executives_url, {"scode": ticker})


def resolve_bse_current_ticker(legacy_ticker: str) -> str | None:
    payload = _request_json(
        EASTMONEY_SUGGEST_URL,
        {
            "input": legacy_ticker,
            "type": "14",
            "token": EASTMONEY_SUGGEST_TOKEN,
        },
    )
    rows = payload.get("QuotationCodeTable", {}).get("Data") or []
    for row in rows:
        code = str(row.get("Code") or "").strip()
        security_type_name = str(row.get("SecurityTypeName") or "").strip()
        market_type = str(row.get("MarketType") or "").strip()
        if code.startswith("920") and (security_type_name == "京A" or market_type == "_TB"):
            return code
    return None


def build_company_source_url(ticker: str, org_id: str | None) -> str:
    params = {"stockCode": ticker}
    if org_id:
        params["orgId"] = org_id
    return f"https://www.cninfo.com.cn/new/disclosure/stock?{urlencode(params)}"


def build_notice_source_url(adjunct_url: str) -> str:
    return f"{settings.cninfo_notice_detail_base_url}{adjunct_url.lstrip('/')}"


def infer_exchange(ticker: str) -> str:
    if ticker.startswith(("000", "001", "002", "003", "300", "301")):
        return "SZSE"
    if ticker.startswith(("600", "601", "603", "605", "688", "689")):
        return "SSE"
    if ticker.startswith(("4", "8", "9", "92")):
        return "BSE"
    return "UNKNOWN"


def normalize_market_segment(ticker: str) -> str:
    if ticker.startswith(("300", "301")):
        return "创业板"
    if ticker.startswith("688"):
        return "科创板"
    if ticker.startswith(("4", "8", "9", "92")):
        return "北交所"
    if ticker.startswith(("000", "001", "002", "003")):
        return "深主板"
    if ticker.startswith(("600", "601", "603", "605")):
        return "沪主板"
    return "其他"


def fetch_notice_page(
    *,
    keyword: str = "",
    page_num: int,
    page_size: int,
    start_date: date,
    end_date: date,
) -> list[AnnouncementEntry]:
    body = {
        "pageNum": str(page_num),
        "pageSize": str(page_size),
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "stock": "",
        "searchkey": keyword,
        "secid": "",
        "category": "category_dshgg_szsh;category_jshgg_szsh;category_qtxx_szsh",
        "trade": "",
        "seDate": f"{start_date.isoformat()}~{end_date.isoformat()}",
        "sortName": "time",
        "sortType": "desc",
        "isHLtitle": "true",
    }
    payload = _post_json(settings.cninfo_notice_search_url, body)
    entries: list[AnnouncementEntry] = []
    for row in payload.get("announcements") or []:
        title = str(row.get("announcementTitle") or "").replace("<em>", "").replace("</em>", "")
        adjunct_url = str(row.get("adjunctUrl") or "").strip()
        announcement_id = str(row.get("announcementId") or "").strip()
        sec_code = str(row.get("secCode") or "").strip()
        if not title or not adjunct_url or not announcement_id or not sec_code:
            continue
        timestamp = int(row.get("announcementTime") or 0)
        announcement_date = date.fromtimestamp(timestamp / 1000) if timestamp else end_date
        entries.append(
            AnnouncementEntry(
                announcement_id=announcement_id,
                sec_code=sec_code,
                sec_name=str(row.get("secName") or "").strip(),
                org_id=str(row.get("orgId") or "").strip() or None,
                title=title,
                announcement_date=announcement_date,
                adjunct_url=adjunct_url,
                source_url=build_notice_source_url(adjunct_url),
                column_id=str(row.get("columnId") or "").strip() or None,
                announcement_type=str(row.get("announcementType") or "").strip() or None,
            )
        )
    return entries


def fetch_management_announcements(
    *,
    days_back: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    keywords: tuple[str, ...] | list[str] | None = None,
    page_limit: int | None = None,
    page_size: int | None = None,
) -> list[AnnouncementEntry]:
    end_date = end_date or date.today()
    start_date = start_date or (end_date - timedelta(days=days_back or settings.notice_sync_days_back))
    raw_keywords = tuple(keywords or settings.notice_keywords or ())
    keywords = tuple(dict.fromkeys(("", *raw_keywords)))
    page_limit = page_limit or settings.notice_sync_page_limit
    page_size = page_size or settings.notice_sync_page_size
    deduped: dict[str, AnnouncementEntry] = {}
    for keyword in keywords:
        for page_num in range(1, page_limit + 1):
            page_entries = fetch_notice_page(
                keyword=keyword,
                page_num=page_num,
                page_size=page_size,
                start_date=start_date,
                end_date=end_date,
            )
            if not page_entries:
                break
            for item in page_entries:
                if item.announcement_id not in deduped and is_management_notice(item.title):
                    deduped[item.announcement_id] = item
            if len(page_entries) < page_size:
                break
    return sorted(deduped.values(), key=lambda item: (item.announcement_date, item.announcement_id), reverse=True)
