from __future__ import annotations

import csv
import hashlib
import html
import re
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from io import StringIO
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, engine, ensure_schema, get_db, session_scope
from app.models import Company
from app.notice_pipeline import (
    reprocess_review_document,
    reprocess_review_item,
    reset_review_document,
    reset_review_item,
    retry_failed_company,
    sync_management_notices,
)
from app.project_memory import ensure_project_memory
from app.schemas import (
    AlertOut,
    BaselineSummaryOut,
    CompanyDetailOut,
    CompanySearchOut,
    CoverageDashboardOut,
    FeedQueryOut,
    LaunchReadinessOut,
    OverviewOut,
    PersonDetailOut,
    PersonSearchOut,
    ProjectMemoryOut,
    ReviewQueueItemOut,
    RuntimePreflightOut,
    WatchlistOut,
)
from app.services import (
    create_watchlist,
    delete_watchlist,
    export_events_rows,
    get_stats,
    get_token_monitor_stats,
    record_page_view,
    get_baseline_summary,
    get_company_detail,
    get_coverage_dashboard,
    get_daily_new_events,
    get_launch_readiness,
    get_overview,
    get_person_detail,
    get_project_memory,
    get_runtime_preflight,
    get_churn_rankings,
    list_alerts,
    list_events,
    list_recent_notice_sync_cards,
    list_recent_companies,
    list_recent_sync_jobs,
    list_review_document_groups,
    list_review_queue,
    list_watchlists,
    mark_alert_read,
    search_companies,
    search_people,
)


app = FastAPI(title=settings.app_name)

static_dir = Path(__file__).resolve().parent / "static"
templates_dir = Path(__file__).resolve().parent / "templates"

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=str(templates_dir))
admin_cookie_serializer = URLSafeSerializer(settings.secret_key, salt="china-succession-admin")
promotion_content_dir = Path(__file__).resolve().parent.parent / "docs" / "promotion" / "content"


def _normalize_pagination(limit: int, offset: int) -> tuple[int, int]:
    safe_limit = min(max(limit or 50, 10), 100)
    safe_offset = max(offset or 0, 0)
    return safe_limit, safe_offset


def _pagination_context(*, total: int, limit: int, offset: int, path: str, params: dict) -> dict:
    total_pages = max((total + limit - 1) // limit, 1)
    current_page = (offset // limit) + 1
    start_item = offset + 1 if total else 0
    end_item = min(offset + limit, total)

    def page_url(target_offset: int) -> str:
        clean_params = {
            key: value
            for key, value in params.items()
            if value not in (None, "", False)
        }
        clean_params["limit"] = limit
        clean_params["offset"] = max(target_offset, 0)
        return f"{path}?{urlencode(clean_params, doseq=True)}"

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "current_page": current_page,
        "total_pages": total_pages,
        "start_item": start_item,
        "end_item": end_item,
        "has_previous": offset > 0,
        "has_next": offset + limit < total,
        "previous_url": page_url(max(offset - limit, 0)),
        "next_url": page_url(offset + limit),
        "first_url": page_url(0),
        "last_url": page_url(max((total_pages - 1) * limit, 0)),
        "page_size_options": [20, 50, 100],
    }


def _build_admin_cookie() -> str:
    return admin_cookie_serializer.dumps({"authenticated": True})


def _is_admin_cookie_valid(cookie_value: str | None) -> bool:
    if not cookie_value:
        return False
    try:
        payload = admin_cookie_serializer.loads(cookie_value)
    except BadSignature:
        return False
    return payload.get("authenticated") is True


_pv_executor = ThreadPoolExecutor(max_workers=2)

# Known bot signatures (substring match).
# NOTE: Core search engine crawlers (Googlebot, Bingbot, Baiduspider, Sogou)
# are intentionally NOT listed here to preserve SEO. Only block data scrapers
# and non-search bots that consume bandwidth without bringing traffic.
_BOT_SIGNATURES = [
    "gptbot",          # OpenAI: trains GPT models, no SEO value
    "mj12bot",         # Majestic SEO: link index scraper
    "googleother",     # Google non-search crawler
    "tlm-audit-scanner", # Unknown scanner
    "ahrefsbot",       # Ahrefs SEO tool
    "semrushbot",      # SEMrush SEO tool
    "dotbot",          # Moz SEO tool
    "yandexbot",       # Yandex (low traffic value for China B2B)
    "exabot",          # Exalead (defunct search engine)
    "facebot",         # Facebook scraper
    "ia_archiver",     # Internet Archive
    "datadog",         # Datadog monitoring crawler
    "uptimerobot",     # Uptime monitoring
    "screaming frog",  # SEO audit tool
]


def _is_bot(user_agent: str | None) -> bool:
    if not user_agent:
        return True
    ua_lower = user_agent.lower()
    return any(sig in ua_lower for sig in _BOT_SIGNATURES)


# --- Rate limiting & anti-scraping (in-memory, per-process) ---
# {ip: [(timestamp, path), ...]}
_request_log: dict[str, list[tuple[float, str]]] = defaultdict(list)
# {ip: [(timestamp, ticker), ...]}
_ticker_scan_log: dict[str, list[tuple[float, str]]] = defaultdict(list)

# Whitelisted IPs (localhost, private ranges could be added here)
_RATE_LIMIT_WHITELIST = {"127.0.0.1", "::1"}


def _is_rate_limited(ip: str, path: str, limit: int = 60, window: int = 60) -> bool:
    """Sliding-window rate limit. Returns True if IP exceeds limit requests in window seconds."""
    if ip in _RATE_LIMIT_WHITELIST:
        return False
    now = time.time()
    log = _request_log[ip]
    # purge stale entries
    cutoff = now - window
    log[:] = [entry for entry in log if entry[0] > cutoff]
    if len(log) >= limit:
        return True
    log.append((now, path))
    return False


def _is_ticker_scanning(ip: str, ticker: str | None, limit: int = 30, window: int = 60) -> bool:
    """Detect rapid enumeration of different tickers on /feed."""
    if not ticker or ip in _RATE_LIMIT_WHITELIST:
        return False
    now = time.time()
    log = _ticker_scan_log[ip]
    cutoff = now - window
    log[:] = [entry for entry in log if entry[0] > cutoff]
    seen = {t for _, t in log}
    if ticker not in seen and len(seen) >= limit:
        return True
    if ticker not in seen:
        log.append((now, ticker))
    return False


def _record_pv_background(path: str, referrer: str | None, user_agent: str | None, ip: str, session_id: str) -> None:
    if _is_bot(user_agent):
        return
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16] if ip else None
        record_page_view(
            db,
            path=path,
            referrer=referrer,
            user_agent=user_agent,
            ip_hash=ip_hash,
            session_id=session_id,
        )
    finally:
        db.close()


def _article_slug(path: Path) -> str:
    return path.stem


def _markdown_to_html(markdown_text: str) -> str:
    """Small, dependency-free Markdown renderer for our controlled promotion articles."""
    blocks: list[str] = []
    lines = markdown_text.splitlines()
    in_list = False
    in_quote = False
    quote_lines: list[str] = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            blocks.append("</ul>")
            in_list = False

    def close_quote() -> None:
        nonlocal in_quote, quote_lines
        if in_quote:
            blocks.append("<blockquote>" + " ".join(quote_lines) + "</blockquote>")
            in_quote = False
            quote_lines = []

    def inline(value: str) -> str:
        escaped = html.escape(value)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
        return escaped

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            close_list()
            close_quote()
            continue
        if line == "---":
            close_list()
            close_quote()
            blocks.append("<hr>")
            continue
        if line.startswith(">"):
            close_list()
            in_quote = True
            quote_lines.append(inline(line.lstrip(">").strip()))
            continue
        close_quote()
        if line.startswith("### "):
            close_list()
            blocks.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("## "):
            close_list()
            blocks.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("# "):
            close_list()
            blocks.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.startswith("- "):
            if not in_list:
                blocks.append("<ul>")
                in_list = True
            blocks.append(f"<li>{inline(line[2:])}</li>")
        elif re.match(r"^\d+\.\s+", line):
            close_list()
            numbered_text = re.sub(r"^\d+\.\s+", "", line)
            blocks.append(f"<p>{inline(numbered_text)}</p>")
        elif line.startswith("|"):
            close_list()
            blocks.append(f"<p><code>{inline(line)}</code></p>")
        else:
            close_list()
            blocks.append(f"<p>{inline(line)}</p>")
    close_list()
    close_quote()
    return "\n".join(blocks)


def _list_promotion_articles() -> list[dict]:
    articles: list[dict] = []
    if not promotion_content_dir.exists():
        return articles
    for path in sorted(promotion_content_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        title = lines[0].lstrip("# ").strip() if lines else path.stem
        summary = next((line.lstrip("> ").strip() for line in lines[1:] if line and not line.startswith("#") and line != "---"), "")
        articles.append({"slug": _article_slug(path), "title": title, "summary": summary, "path": path})
    return articles


def _get_promotion_article(slug: str) -> dict | None:
    safe_slug = re.sub(r"[^a-zA-Z0-9_-]", "", slug)
    path = promotion_content_dir / f"{safe_slug}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = lines[0].lstrip("# ").strip() if lines else safe_slug
    summary = next((line.lstrip("> ").strip() for line in lines[1:] if line and not line.startswith("#") and line != "---"), "")
    return {"slug": safe_slug, "title": title, "summary": summary, "html": _markdown_to_html(text)}


@app.middleware("http")
async def require_admin_login(request: Request, call_next):
    path = request.url.path
    user_agent = request.headers.get("user-agent")

    # Block known bad bots before any processing
    if _is_bot(user_agent):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)

    # Silently drop CMS scanner probes (WordPress, Joomla, etc.)
    if path.startswith("/wp-") or path in {"/xmlrpc.php", "/administrator", "/admin.php"}:
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    # Rate limiting
    client_ip = request.client.host if request.client else ""
    api_limit = 30 if path.startswith("/api/") else 60
    if _is_rate_limited(client_ip, path, limit=api_limit, window=60):
        return JSONResponse({"detail": "Too Many Requests"}, status_code=429)

    # Anti-ticker-scanning on /feed
    if path == "/feed":
        ticker = request.query_params.get("ticker")
        if _is_ticker_scanning(client_ip, ticker, limit=30, window=60):
            return JSONResponse({"detail": "Too Many Requests"}, status_code=429)

    # Get or create anonymous visitor ID
    visitor_id = request.cookies.get("visitor_id")
    is_new_visitor = False
    if not visitor_id:
        visitor_id = str(uuid.uuid4())
        is_new_visitor = True
    request.state.visitor_id = visitor_id

    # Auth check
    if not settings.admin_password:
        response = await call_next(request)
    else:
        public_paths = {
            "/", "/feed", "/companies", "/people", "/watchlists",
            "/blog",
            "/login", "/healthz", "/readyz",
            "/robots.txt", "/sitemap.xml", "/favicon.ico", "/favicon.png",
            "/exports/events.csv",
        }
        is_public = (
            path.startswith("/static")
            or path.startswith("/companies/")
            or path.startswith("/people/")
            or path.startswith("/blog/")
            or path in public_paths
        )

        if is_public or _is_admin_cookie_valid(request.cookies.get("admin_auth")):
            response = await call_next(request)
        elif path.startswith("/api/") or path.startswith("/exports/"):
            response = JSONResponse({"detail": "Unauthorized"}, status_code=401)
        else:
            next_path = path
            if request.url.query:
                next_path = f"{next_path}?{request.url.query}"
            response = RedirectResponse(url=f"/login?next={next_path}", status_code=303)

    # Set visitor_id cookie for new visitors
    if is_new_visitor:
        response.set_cookie(
            key="visitor_id",
            value=visitor_id,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="lax",
        )

    # Record page view (skip static assets, health checks, bots)
    if not path.startswith("/static") and path not in {"/healthz", "/readyz", "/robots.txt", "/sitemap.xml"}:
        ip = request.client.host if request.client else ""
        _pv_executor.submit(
            _record_pv_background,
            path,
            request.headers.get("referer"),
            request.headers.get("user-agent"),
            ip,
            visitor_id,
        )

    return response


@app.on_event("startup")
def on_startup() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    ensure_project_memory()
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    with session_scope() as db:
        company_count = db.scalar(select(func.count()).select_from(Company)) or 0
        if company_count == 0:
            raise RuntimeError("公司全集为空，请先运行 `python -m app.tasks init-universe` 初始化数据。")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    if not settings.admin_password:
        return RedirectResponse(url="/", status_code=303)
    if _is_admin_cookie_valid(request.cookies.get("admin_auth")):
        return RedirectResponse(url=next or "/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"next_path": next, "error_message": ""})


@app.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, password: str = Form(...), next_path: str = Form(default="/")):
    if not settings.admin_password:
        return RedirectResponse(url="/", status_code=303)
    if password != settings.admin_password:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next_path": next_path or "/", "error_message": "密码不正确，请重试。"},
            status_code=401,
        )
    response = RedirectResponse(url=next_path or "/", status_code=303)
    response.set_cookie(
        "admin_auth",
        _build_admin_cookie(),
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )
    return response


@app.post("/logout")
def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("admin_auth")
    return response


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    overview = get_overview(db)
    companies = list_recent_companies(db)
    rankings = get_churn_rankings(db)[:5]
    memory = get_project_memory()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"overview": overview, "companies": companies, "rankings": rankings, "memory": memory},
    )


@app.get("/blog", response_class=HTMLResponse)
def blog_page(request: Request):
    articles = _list_promotion_articles()
    return templates.TemplateResponse(request, "blog.html", {"articles": articles})


@app.get("/blog/{slug}", response_class=HTMLResponse)
def blog_article_page(slug: str, request: Request):
    article = _get_promotion_article(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return templates.TemplateResponse(request, "blog_article.html", {"article": article})


@app.get("/coverage", response_class=HTMLResponse)
def coverage_page(request: Request, db: Session = Depends(get_db)):
    coverage = get_coverage_dashboard(db)
    sync_jobs = list_recent_sync_jobs(db)
    return templates.TemplateResponse(request, "coverage.html", {"coverage": coverage, "sync_jobs": sync_jobs})


@app.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request, db: Session = Depends(get_db)):
    stats = get_stats(db)
    return templates.TemplateResponse(request, "stats.html", {"stats": stats})


@app.get("/token-monitor", response_class=HTMLResponse)
def token_monitor_page(request: Request, db: Session = Depends(get_db)):
    token_stats = get_token_monitor_stats(db)
    return templates.TemplateResponse(request, "token_monitor.html", {"token_stats": token_stats})


@app.get("/launch-readiness", response_class=HTMLResponse)
def launch_readiness_page(request: Request, db: Session = Depends(get_db)):
    readiness = get_launch_readiness(db)
    return templates.TemplateResponse(request, "launch_readiness.html", {"readiness": readiness})


@app.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    db.scalar(select(func.count()).select_from(Company))
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@app.get("/readyz")
def readyz(db: Session = Depends(get_db)):
    preflight = get_runtime_preflight(db)
    status_code = 200 if preflight.overall_status == "ready" else 503
    return JSONResponse(preflight.model_dump(), status_code=status_code)


@app.get("/robots.txt")
def robots_txt():
    content = (settings.data_dir.parent / "app" / "static" / "robots.txt").read_text(encoding="utf-8")
    return StreamingResponse(iter([content]), media_type="text/plain")


@app.get("/sitemap.xml")
def sitemap_xml():
    content = (settings.data_dir.parent / "app" / "static" / "sitemap.xml").read_text(encoding="utf-8")
    return StreamingResponse(iter([content]), media_type="application/xml")


@app.get("/favicon.ico")
def favicon_ico():
    favicon_path = static_dir / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/x-icon")
    raise HTTPException(status_code=404, detail="Not found")


@app.get("/feed", response_class=HTMLResponse)
def feed_page(
    request: Request,
    role: str | None = None,
    event_type: str | None = None,
    ticker: str | None = None,
    q: str | None = None,
    include_review: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit, offset = _normalize_pagination(limit, offset)
    feed = list_events(
        db,
        limit=limit,
        offset=offset,
        role=role,
        event_type=event_type,
        ticker=ticker,
        q=q,
        include_review=include_review,
    )
    return templates.TemplateResponse(
        request,
        "feed.html",
        {
            "feed": feed,
            "filters": {
                "role": role or "",
                "event_type": event_type or "",
                "ticker": ticker or "",
                "q": q or "",
                "include_review": include_review,
                "limit": limit,
                "offset": offset,
            },
            "pagination": _pagination_context(
                total=feed.total,
                limit=limit,
                offset=offset,
                path="/feed",
                params={
                    "role": role,
                    "event_type": event_type,
                    "ticker": ticker,
                    "q": q,
                    "include_review": "true" if include_review else None,
                },
            ),
        },
    )


@app.get("/companies", response_class=HTMLResponse)
def companies_page(
    request: Request,
    q: str | None = None,
    exchange: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit, offset = _normalize_pagination(limit, offset)
    result = search_companies(db, q=q, exchange=exchange, baseline_status=status, limit=limit, offset=offset)
    return templates.TemplateResponse(
        request,
        "companies.html",
        {
            "result": result,
            "filters": {"q": q or "", "exchange": exchange or "", "status": status or "", "limit": limit, "offset": offset},
            "pagination": _pagination_context(
                total=result.total,
                limit=limit,
                offset=offset,
                path="/companies",
                params={"q": q, "exchange": exchange, "status": status},
            ),
        },
    )


@app.get("/people", response_class=HTMLResponse)
def people_page(
    request: Request,
    q: str | None = None,
    role: str | None = None,
    active_only: bool = True,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit, offset = _normalize_pagination(limit, offset)
    result = search_people(db, q=q, role=role, active_only=active_only, limit=limit, offset=offset)
    return templates.TemplateResponse(
        request,
        "people_list.html",
        {
            "result": result,
            "filters": {
                "q": q or "",
                "role": role or "",
                "active_only": active_only,
                "limit": limit,
                "offset": offset,
            },
            "pagination": _pagination_context(
                total=result.total,
                limit=limit,
                offset=offset,
                path="/people",
                params={"q": q, "role": role, "active_only": "true" if active_only else None},
            ),
        },
    )


@app.get("/watchlists", response_class=HTMLResponse)
def watchlists_page(request: Request, db: Session = Depends(get_db)):
    session_id = request.state.visitor_id
    return templates.TemplateResponse(
        request,
        "watchlists.html",
        {"watchlists": list_watchlists(db, session_id=session_id), "alerts": list_alerts(db, session_id=session_id, limit=30)},
    )


@app.get("/review", response_class=HTMLResponse)
def review_page(request: Request, db: Session = Depends(get_db)):
    groups = list_review_document_groups(db, limit=500)
    pending_item_count = sum(group["review_count"] for group in groups)
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "groups": groups,
            "pending_item_count": pending_item_count,
            "pending_document_count": len(groups),
            "sync_jobs": list_recent_sync_jobs(db),
        },
    )


@app.get("/daily-events", response_class=HTMLResponse)
def daily_events_page(request: Request, day: date | None = None, db: Session = Depends(get_db)):
    daily = get_daily_new_events(db, day=day)
    return templates.TemplateResponse(
        request,
        "daily_events.html",
        {
            "daily": daily,
            "sync_cards": list_recent_notice_sync_cards(db, limit=8),
            "notice_sync_strategy": {
                "summary": "系统每 30 分钟自动检查一次管理层相关公告。",
                "window": "每次回看最近 3 天公告，处理延迟披露、网络失败和人工审核放行后的补记。",
                "event_rule": "本页只记录进入“已发布”的事件，自动发布和人工审核通过都会计入对应日期。",
            },
        },
    )


@app.get("/memory", response_class=HTMLResponse)
def memory_page(request: Request):
    return templates.TemplateResponse(request, "memory.html", {"memory": get_project_memory()})


@app.get("/companies/{ticker}", response_class=HTMLResponse)
def company_page(ticker: str, request: Request, db: Session = Depends(get_db)):
    detail = get_company_detail(db, ticker)
    if not detail:
        raise HTTPException(status_code=404, detail="Company not found")
    return templates.TemplateResponse(request, "company.html", {"company": detail})


@app.get("/people/{person_id}", response_class=HTMLResponse)
def person_page(person_id: int, request: Request, db: Session = Depends(get_db)):
    detail = get_person_detail(db, person_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Person not found")
    return templates.TemplateResponse(request, "person.html", {"person": detail})


@app.post("/watchlists/create")
def watchlist_create_form(
    request: Request,
    target_type: str = Form(...),
    ticker: str | None = Form(default=None),
    person_id: str | None = Form(default=None),
    role_canonical: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    try:
        parsed_person_id = int(person_id) if person_id and person_id.strip() else None
        create_watchlist(
            db,
            session_id=request.state.visitor_id,
            target_type=target_type,
            ticker=ticker.strip() if ticker else None,
            person_id=parsed_person_id,
            role_canonical=role_canonical,
            notes=notes.strip() if notes else None,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url="/watchlists", status_code=303)


@app.post("/watchlists/{watchlist_id}/delete")
def watchlist_delete_form(watchlist_id: int, request: Request, db: Session = Depends(get_db)):
    if not delete_watchlist(db, watchlist_id, session_id=request.state.visitor_id):
        raise HTTPException(status_code=404, detail="Watchlist not found")
    db.commit()
    return RedirectResponse(url="/watchlists", status_code=303)


@app.post("/alerts/{alert_id}/read")
def alert_mark_read_form(alert_id: int, request: Request, db: Session = Depends(get_db)):
    if not mark_alert_read(db, alert_id, session_id=request.state.visitor_id):
        raise HTTPException(status_code=404, detail="Alert not found")
    db.commit()
    return RedirectResponse(url="/watchlists", status_code=303)


@app.post("/review/{review_id}/approve")
def review_approve_form(review_id: int, db: Session = Depends(get_db)):
    item = reset_review_item(db, review_id, status="approved", notes="已在后台确认发布")
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    db.commit()
    return RedirectResponse(url="/review", status_code=303)


@app.post("/review/{review_id}/reject")
def review_reject_form(review_id: int, db: Session = Depends(get_db)):
    item = reset_review_item(db, review_id, status="rejected", notes="已判定为无效或待补充")
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    db.commit()
    return RedirectResponse(url="/review", status_code=303)


@app.post("/review/{review_id}/reprocess")
def review_reprocess_form(review_id: int, db: Session = Depends(get_db)):
    result = reprocess_review_item(db, review_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Review item not found")
    db.commit()
    return RedirectResponse(url="/review", status_code=303)


@app.post("/review/document/{source_document_id}/approve")
def review_document_approve_form(source_document_id: int, db: Session = Depends(get_db)):
    resolved_count = reset_review_document(db, source_document_id, status="approved", notes="已在后台按公告批量确认发布")
    if resolved_count == 0:
        raise HTTPException(status_code=404, detail="Review document not found")
    db.commit()
    return RedirectResponse(url="/review", status_code=303)


@app.post("/review/document/{source_document_id}/reject")
def review_document_reject_form(source_document_id: int, db: Session = Depends(get_db)):
    resolved_count = reset_review_document(db, source_document_id, status="rejected", notes="已按公告批量判定为无效或待补充")
    if resolved_count == 0:
        raise HTTPException(status_code=404, detail="Review document not found")
    db.commit()
    return RedirectResponse(url="/review", status_code=303)


@app.post("/review/document/{source_document_id}/reprocess")
def review_document_reprocess_form(source_document_id: int, db: Session = Depends(get_db)):
    result = reprocess_review_document(db, source_document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Review document not found")
    db.commit()
    return RedirectResponse(url="/review", status_code=303)


@app.post("/review/retry-company/{ticker}")
def retry_company_form(ticker: str, db: Session = Depends(get_db)):
    if not retry_failed_company(db, ticker):
        raise HTTPException(status_code=404, detail="Company not found")
    db.commit()
    return RedirectResponse(url="/coverage", status_code=303)


@app.post("/sync/notices")
def sync_notices_form(days_back: int = Form(default=settings.notice_sync_days_back), db: Session = Depends(get_db)):
    sync_management_notices(db, days_back=days_back)
    db.commit()
    return RedirectResponse(url="/feed", status_code=303)


@app.get("/exports/events.csv")
def export_events_csv(
    request: Request,
    role: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    ticker: str | None = Query(default=None),
    include_review: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    include_review = include_review and _is_admin_cookie_valid(request.cookies.get("admin_auth"))
    rows = export_events_rows(db, role=role, event_type=event_type, ticker=ticker, include_review=include_review)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["公司", "代码", "人物", "角色", "事件", "状态", "公告日期", "生效日期", "置信度", "证据", "来源"])
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="china_succession_events.csv"'},
    )


@app.get("/api/project-memory", response_model=ProjectMemoryOut)
def project_memory_api():
    return get_project_memory()


@app.get("/api/overview", response_model=OverviewOut)
def overview_api(db: Session = Depends(get_db)):
    return get_overview(db)


@app.get("/api/baseline/summary", response_model=BaselineSummaryOut)
def baseline_summary_api(db: Session = Depends(get_db)):
    return get_baseline_summary(db)


@app.get("/api/coverage", response_model=CoverageDashboardOut)
def coverage_api(db: Session = Depends(get_db)):
    return get_coverage_dashboard(db)


@app.get("/api/launch-readiness", response_model=LaunchReadinessOut)
def launch_readiness_api(db: Session = Depends(get_db)):
    return get_launch_readiness(db)


@app.get("/api/preflight", response_model=RuntimePreflightOut)
def preflight_api(db: Session = Depends(get_db)):
    return get_runtime_preflight(db)


@app.get("/api/feed/events", response_model=FeedQueryOut)
def feed_api(
    role: str | None = None,
    event_type: str | None = None,
    ticker: str | None = None,
    q: str | None = None,
    include_review: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return list_events(
        db,
        limit=limit,
        offset=offset,
        role=role,
        event_type=event_type,
        ticker=ticker,
        q=q,
        include_review=include_review,
    )


@app.get("/api/events", response_model=FeedQueryOut)
def events_api(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return list_events(db, limit=limit, offset=offset)


@app.get("/api/daily-events")
def daily_events_api(day: date | None = None, db: Session = Depends(get_db)):
    return get_daily_new_events(db, day=day)


@app.get("/api/companies", response_model=CompanySearchOut)
def companies_api(
    q: str | None = None,
    exchange: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return search_companies(db, q=q, exchange=exchange, baseline_status=status, limit=limit, offset=offset)


@app.get("/api/people", response_model=PersonSearchOut)
def people_api(
    q: str | None = None,
    role: str | None = None,
    active_only: bool = True,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return search_people(db, q=q, role=role, active_only=active_only, limit=limit, offset=offset)


@app.get("/api/companies/{ticker}", response_model=CompanyDetailOut)
def company_api(ticker: str, db: Session = Depends(get_db)):
    detail = get_company_detail(db, ticker)
    if not detail:
        raise HTTPException(status_code=404, detail="Company not found")
    return detail


@app.get("/api/people/{person_id}", response_model=PersonDetailOut)
def person_api(person_id: int, db: Session = Depends(get_db)):
    detail = get_person_detail(db, person_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Person not found")
    return detail


@app.get("/api/rankings/churn")
def churn_rankings_api(db: Session = Depends(get_db)):
    return get_churn_rankings(db)


@app.get("/api/watchlists", response_model=list[WatchlistOut])
def watchlists_api(request: Request, db: Session = Depends(get_db)):
    return list_watchlists(db, session_id=request.state.visitor_id)


@app.post("/api/watchlists", response_model=WatchlistOut)
def watchlists_create_api(
    request: Request,
    target_type: str,
    ticker: str | None = None,
    person_id: int | None = None,
    role_canonical: str | None = None,
    notes: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        item = create_watchlist(
            db,
            session_id=request.state.visitor_id,
            target_type=target_type,
            ticker=ticker,
            person_id=person_id,
            role_canonical=role_canonical,
            notes=notes,
        )
        db.commit()
        return item
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/watchlists/{watchlist_id}")
def watchlists_delete_api(watchlist_id: int, request: Request, db: Session = Depends(get_db)):
    if not delete_watchlist(db, watchlist_id, session_id=request.state.visitor_id):
        raise HTTPException(status_code=404, detail="Watchlist not found")
    db.commit()
    return {"ok": True}


@app.get("/api/alerts", response_model=list[AlertOut])
def alerts_api(request: Request, status: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    return list_alerts(db, session_id=request.state.visitor_id, status=status, limit=limit)


@app.post("/api/alerts/{alert_id}/read")
def alerts_read_api(alert_id: int, db: Session = Depends(get_db)):
    if not mark_alert_read(db, alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")
    db.commit()
    return {"ok": True}


@app.get("/api/review/queue", response_model=list[ReviewQueueItemOut])
def review_queue_api(status: str = "pending", limit: int = 100, db: Session = Depends(get_db)):
    return list_review_queue(db, status=status, limit=limit)


@app.get("/api/review/groups")
def review_groups_api(status: str = "pending", limit: int = 500, db: Session = Depends(get_db)):
    return list_review_document_groups(db, status=status, limit=limit)


@app.post("/api/review/queue/{review_id}/approve")
def review_queue_approve_api(review_id: int, db: Session = Depends(get_db)):
    item = reset_review_item(db, review_id, status="approved", notes="API 审核通过")
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    db.commit()
    return {"ok": True}


@app.post("/api/review/queue/{review_id}/reject")
def review_queue_reject_api(review_id: int, db: Session = Depends(get_db)):
    item = reset_review_item(db, review_id, status="rejected", notes="API 审核驳回")
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    db.commit()
    return {"ok": True}


@app.post("/api/review/queue/{review_id}/reprocess")
def review_queue_reprocess_api(review_id: int, db: Session = Depends(get_db)):
    result = reprocess_review_item(db, review_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Review item not found")
    db.commit()
    return {"status": "reprocessed", "id": review_id, "created_events": result[0], "pending_review": result[1]}


@app.post("/api/review/documents/{source_document_id}/approve")
def review_document_approve_api(source_document_id: int, db: Session = Depends(get_db)):
    resolved_count = reset_review_document(db, source_document_id, status="approved", notes="API 按公告批量审核通过")
    if resolved_count == 0:
        raise HTTPException(status_code=404, detail="Review document not found")
    db.commit()
    return {"ok": True, "resolved_count": resolved_count}


@app.post("/api/review/documents/{source_document_id}/reject")
def review_document_reject_api(source_document_id: int, db: Session = Depends(get_db)):
    resolved_count = reset_review_document(db, source_document_id, status="rejected", notes="API 按公告批量审核驳回")
    if resolved_count == 0:
        raise HTTPException(status_code=404, detail="Review document not found")
    db.commit()
    return {"ok": True, "resolved_count": resolved_count}


@app.post("/api/review/documents/{source_document_id}/reprocess")
def review_document_reprocess_api(source_document_id: int, db: Session = Depends(get_db)):
    result = reprocess_review_document(db, source_document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Review document not found")
    db.commit()
    return {"status": "reprocessed", "source_document_id": source_document_id, "created_events": result[0], "pending_review": result[1]}


@app.post("/api/review/retry-company/{ticker}")
def review_retry_company_api(ticker: str, db: Session = Depends(get_db)):
    if not retry_failed_company(db, ticker):
        raise HTTPException(status_code=404, detail="Company not found")
    db.commit()
    return {"ok": True}


@app.get("/api/token-monitor")
def token_monitor_api(db: Session = Depends(get_db)):
    return get_token_monitor_stats(db)
