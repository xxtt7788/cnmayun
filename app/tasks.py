from __future__ import annotations

import argparse
import sys
import time
from datetime import date

from app.bootstrap import (
    count_zero_snapshot_issuers,
    count_unsynced_companies,
    ensure_company_universe,
    list_unsynced_tickers,
    repair_zero_snapshot_companies,
    sync_company_baseline,
)
from app.config import settings
from app.db import Base, engine, ensure_schema, session_scope
from app.notice_pipeline import backfill_management_notices, reprocess_pending_review_documents, sync_management_notices
from app.project_memory import ensure_project_memory
from app.services import get_launch_readiness, get_runtime_preflight
from runner.enhance_persons_from_eastmoney import main as enhance_persons_main
from runner.sync_executives_from_eastmoney import main as sync_executives_from_eastmoney_main


def reset_database() -> None:
    if settings.database_url.startswith("sqlite:///./"):
        db_path = settings.base_dir / settings.database_url.removeprefix("sqlite:///./")
        if db_path.exists():
            db_path.unlink()


def refresh_universe() -> int:
    with session_scope() as db:
        return ensure_company_universe(db)


def run_sync_baseline(limit: int | None, workers: int) -> None:
    with session_scope() as db:
        run = sync_company_baseline(db, limit=limit, max_workers=workers)
        print(
            f"公司档案/高管基线同步完成：请求 {run.requested_company_count} 家，成功 {run.success_company_count} 家，"
            f"失败 {run.failed_company_count} 家，状态 {run.status}"
        )


def run_sync_remaining_baseline(batch_size: int, max_rounds: int, workers: int) -> None:
    total_success = 0
    total_failed = 0
    for round_index in range(1, max_rounds + 1):
        with session_scope() as db:
            remaining = count_unsynced_companies(db)
            print(f"第 {round_index} 轮开始，剩余未同步公司：{remaining}")
            if remaining == 0:
                break

            tickers = list_unsynced_tickers(db, batch_size)
            if not tickers:
                break

            run = sync_company_baseline(db, tickers=tickers, max_workers=workers)
            total_success += run.success_company_count
            total_failed += run.failed_company_count
            print(
                f"第 {round_index} 轮完成：请求 {run.requested_company_count} 家，成功 {run.success_company_count} 家，"
                f"失败 {run.failed_company_count} 家，状态 {run.status}"
            )

            if run.success_company_count == 0 and run.failed_company_count == run.requested_company_count:
                print("本轮没有取得进展，停止后续重试。")
                break

    with session_scope() as db:
        remaining = count_unsynced_companies(db)
        print(f"剩余未同步公司：{remaining}，累计成功 {total_success} 家，累计失败 {total_failed} 家")


def run_sync_notices(days_back: int) -> None:
    with session_scope() as db:
        run = sync_management_notices(db, days_back=days_back)
        print(
            f"公告同步完成：请求 {run.requested_count} 篇，成功 {run.success_count} 篇，"
            f"失败 {run.failed_count} 篇，状态 {run.status}"
        )


def run_repair_zero_snapshots(limit: int | None, workers: int, active_only: bool) -> None:
    with session_scope() as db:
        result = repair_zero_snapshot_companies(db, limit=limit, max_workers=workers, active_only=active_only)
        if not result:
            remaining = count_zero_snapshot_issuers(db, active_only=active_only)
            print(f"没有待修复的零快照发行人。当前剩余：{remaining}")
            return
        print(
            f"零快照修复完成：请求 {result.requested_company_count} 家，"
            f"成功 {result.run.success_company_count} 家，失败 {result.run.failed_company_count} 家，"
            f"修复发行人 {result.repaired_issuer_count} 个，剩余 {result.remaining_zero_snapshot_issuers} 个"
        )


def run_backfill_notices(start_date: date, end_date: date, window_days: int, page_limit: int) -> None:
    with session_scope() as db:
        summary = backfill_management_notices(
            db,
            start_date=start_date,
            end_date=end_date,
            window_days=window_days,
            page_limit=page_limit,
        )
        print(
            f"历史公告回填完成：窗口 {summary.window_count} 个，请求 {summary.requested_count} 篇，"
            f"处理 {summary.processed_count} 篇，成功 {summary.success_count} 篇，失败 {summary.failed_count} 篇，"
            f"失败窗口 {summary.failed_window_count} 个，"
            f"当前已发布事件 {summary.published_event_count} 条，待审核 {summary.pending_review_count} 条"
        )


def run_reprocess_pending_reviews(limit: int) -> None:
    with session_scope() as db:
        processed_count, created_count, review_count = reprocess_pending_review_documents(db, limit=limit)
        print(
            f"待审核公告重新抽取完成：处理 {processed_count} 条，生成事件 {created_count} 条，"
            f"仍需审核 {review_count} 条"
        )


def run_ops_loop(
    *,
    notice_days_back: int,
    notice_interval_minutes: int,
    notice_page_limit: int,
    zero_snapshot_batch_size: int,
    zero_snapshot_interval_hours: int,
    zero_snapshot_workers: int,
) -> None:
    last_zero_snapshot_repair = 0.0
    while True:
        with session_scope() as db:
            run = sync_management_notices(db, days_back=notice_days_back, page_limit=notice_page_limit)
            print(
                f"[ops-loop] 公告同步：请求 {run.requested_count} 篇，处理 {run.processed_count} 篇，"
                f"成功 {run.success_count} 篇，失败 {run.failed_count} 篇"
            )

        now = time.time()
        if now - last_zero_snapshot_repair >= zero_snapshot_interval_hours * 3600:
            with session_scope() as db:
                result = repair_zero_snapshot_companies(
                    db,
                    limit=zero_snapshot_batch_size,
                    max_workers=zero_snapshot_workers,
                    active_only=True,
                )
                if result:
                    print(
                        f"[ops-loop] 零快照修复：请求 {result.requested_company_count} 家，"
                        f"修复发行人 {result.repaired_issuer_count} 个，剩余 {result.remaining_zero_snapshot_issuers} 个"
                    )
                else:
                    print("[ops-loop] 当前没有待修复的活跃零快照发行人。")
            last_zero_snapshot_repair = now

        time.sleep(max(notice_interval_minutes, 1) * 60)


def run_preflight(strict: bool) -> None:
    with session_scope() as db:
        readiness = get_launch_readiness(db)
        preflight = get_runtime_preflight(db)

    print(f"运行环境：{preflight.environment}")
    print(f"数据库后端：{preflight.database_backend}")
    print(f"当前状态：{preflight.overall_status}")
    print("检查项：")
    for item in preflight.checks:
        print(f"- [{item.status}] {item.name}: {item.detail}")

    print("上线准备度：")
    print(f"- 原始公司全集：{readiness.synced_companies}/{readiness.raw_total_companies}")
    print(f"- 去重后发行人：{readiness.canonical_companies}")
    print(f"- 去重后零快照：{readiness.canonical_zero_snapshot_companies}")
    print(f"- 已发布事件：{readiness.published_event_count}")
    print(f"- 待审核：{readiness.pending_review_count}")

    if readiness.blocking_issues:
        print("阻塞项：")
        for issue in readiness.blocking_issues:
            print(f"- {issue}")
    else:
        print("阻塞项：无")

    if strict and preflight.overall_status != "ready":
        raise SystemExit(2)


def main() -> None:
    parser = argparse.ArgumentParser(description="中国上市公司高管与董事变动同步工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-universe", help="初始化/刷新上市公司全集")
    init_parser.add_argument("--reset-db", action="store_true", help="重建数据库")

    sync_baseline_parser = subparsers.add_parser("sync-baseline", help="同步公司档案与当前高管基线")
    sync_baseline_parser.add_argument("--limit", type=int, default=None, help="限制同步公司数量")
    sync_baseline_parser.add_argument("--workers", type=int, default=6, help="并发抓取线程数")
    sync_baseline_parser.add_argument("--reset-db", action="store_true", help="重建数据库")

    sync_remaining_parser = subparsers.add_parser("sync-remaining-baseline", help="多轮补齐剩余公司档案与高管基线")
    sync_remaining_parser.add_argument("--batch-size", type=int, default=100, help="每轮处理公司数")
    sync_remaining_parser.add_argument("--max-rounds", type=int, default=20, help="最多重试轮数")
    sync_remaining_parser.add_argument("--workers", type=int, default=2, help="并发抓取线程数")
    sync_remaining_parser.add_argument("--reset-db", action="store_true", help="重建数据库")

    sync_notice_parser = subparsers.add_parser("sync-notices", help="同步管理层相关公告并抽取事件")
    sync_notice_parser.add_argument("--days-back", type=int, default=settings.notice_sync_days_back, help="向前回溯天数")
    sync_notice_parser.add_argument("--reset-db", action="store_true", help="重建数据库")

    repair_zero_parser = subparsers.add_parser("repair-zero-snapshots", help="定向修复零快照发行人")
    repair_zero_parser.add_argument("--limit", type=int, default=None, help="限制修复的发行人数")
    repair_zero_parser.add_argument("--workers", type=int, default=4, help="并发抓取线程数")
    repair_zero_parser.add_argument("--include-inactive", action="store_true", help="包含非活跃发行人")
    repair_zero_parser.add_argument("--reset-db", action="store_true", help="重建数据库")

    backfill_parser = subparsers.add_parser("backfill-notices", help="按时间窗口回填历史管理层公告")
    backfill_parser.add_argument("--start-date", type=date.fromisoformat, required=True, help="回填开始日期 YYYY-MM-DD")
    backfill_parser.add_argument("--end-date", type=date.fromisoformat, required=True, help="回填结束日期 YYYY-MM-DD")
    backfill_parser.add_argument("--window-days", type=int, default=30, help="每个回填窗口的天数")
    backfill_parser.add_argument("--page-limit", type=int, default=20, help="每个关键词每个窗口最多抓取页数")
    backfill_parser.add_argument("--reset-db", action="store_true", help="重建数据库")

    reprocess_parser = subparsers.add_parser("reprocess-reviews", help="用最新规则和 AI 兜底重新处理待审核公告")
    reprocess_parser.add_argument("--limit", type=int, default=100, help="最多处理待审核条数")
    reprocess_parser.add_argument("--reset-db", action="store_true", help="重建数据库")

    ops_loop_parser = subparsers.add_parser("ops-loop", help="持续自动抓取公告并定期修复零快照公司")
    ops_loop_parser.add_argument("--notice-days-back", type=int, default=3, help="每轮公告同步回看天数")
    ops_loop_parser.add_argument("--notice-interval-minutes", type=int, default=30, help="公告同步间隔分钟")
    ops_loop_parser.add_argument("--notice-page-limit", type=int, default=12, help="每轮公告同步每个关键词页数上限")
    ops_loop_parser.add_argument("--zero-snapshot-batch-size", type=int, default=40, help="每轮零快照修复发行人数")
    ops_loop_parser.add_argument("--zero-snapshot-interval-hours", type=int, default=6, help="零快照修复间隔小时")
    ops_loop_parser.add_argument("--zero-snapshot-workers", type=int, default=4, help="零快照修复并发线程数")
    ops_loop_parser.add_argument("--reset-db", action="store_true", help="重建数据库")

    preflight_parser = subparsers.add_parser("preflight", help="输出正式上线前的运行检查结果")
    preflight_parser.add_argument("--strict", action="store_true", help="存在阻塞项时返回非零退出码")
    preflight_parser.add_argument("--reset-db", action="store_true", help="重建数据库")

    enhance_persons_parser = subparsers.add_parser("enhance-persons", help="通过东方财富 API 补全高管 gender/birth_year/education")
    enhance_persons_parser.add_argument("--reset-db", action="store_true", help="重建数据库")

    sync_em_parser = subparsers.add_parser("sync-executives-eastmoney", help="通过东方财富 API 全量同步公司高管快照")
    sync_em_parser.add_argument("--reset-db", action="store_true", help="重建数据库")

    args = parser.parse_args()

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    ensure_project_memory()
    if args.reset_db:
        reset_database()

    Base.metadata.create_all(bind=engine)
    ensure_schema()
    if args.command != "preflight":
        total = refresh_universe()
        print(f"已载入上市公司全集：{total}")

    if args.command == "sync-baseline":
        run_sync_baseline(args.limit, args.workers)
    elif args.command == "sync-remaining-baseline":
        run_sync_remaining_baseline(args.batch_size, args.max_rounds, args.workers)
    elif args.command == "sync-notices":
        run_sync_notices(args.days_back)
    elif args.command == "repair-zero-snapshots":
        run_repair_zero_snapshots(args.limit, args.workers, not args.include_inactive)
    elif args.command == "backfill-notices":
        run_backfill_notices(args.start_date, args.end_date, args.window_days, args.page_limit)
    elif args.command == "reprocess-reviews":
        run_reprocess_pending_reviews(args.limit)
    elif args.command == "ops-loop":
        run_ops_loop(
            notice_days_back=args.notice_days_back,
            notice_interval_minutes=args.notice_interval_minutes,
            notice_page_limit=args.notice_page_limit,
            zero_snapshot_batch_size=args.zero_snapshot_batch_size,
            zero_snapshot_interval_hours=args.zero_snapshot_interval_hours,
            zero_snapshot_workers=args.zero_snapshot_workers,
        )
    elif args.command == "preflight":
        run_preflight(args.strict)
    elif args.command == "enhance-persons":
        enhance_persons_main()
    elif args.command == "sync-executives-eastmoney":
        sync_executives_from_eastmoney_main()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"任务执行失败：{exc}", file=sys.stderr)
        raise
