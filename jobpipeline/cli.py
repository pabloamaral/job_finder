"""CLI review queue — the human-in-the-loop interface.

This is the "review and one-click submit" surface. It does NOT submit
applications anywhere; it stages scored matches with tailored docs attached
so the owner can review, then mark status by hand.

Commands:
    python -m jobpipeline.cli discover         # run a discovery cycle
    python -m jobpipeline.cli list             # show the review queue
    python -m jobpipeline.cli list --status new --min-score 70
    python -m jobpipeline.cli show <job_id>    # full detail + tailored docs
    python -m jobpipeline.cli status <job_id> <new|reviewed|applied|rejected|skipped>
    python -m jobpipeline.cli stats            # pipeline state summary

Build out a richer dashboard (e.g. a small Flask/Textual app) on top of the
same Tracker queries when you take this into Claude Code.
"""

from __future__ import annotations

import argparse
import logging
import sys

from jobpipeline import config
from jobpipeline.filters import is_remote_listing
from jobpipeline.models import ApplicationStatus
from jobpipeline.pipeline import run_discovery
from jobpipeline.tracker import Tracker


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


def cmd_discover(args, tracker: Tracker) -> None:
    summary = run_discovery(tracker, tailor=not args.no_tailor)
    msg = (f"Discovered: {summary['discovered']}  "
           f"New: {summary['new']}  Tailored: {summary['tailored']}")
    if summary.get("non_remote_skipped"):
        msg += f"  (non-remote skipped: {summary['non_remote_skipped']})"
    print(msg)


def cmd_list(args, tracker: Tracker) -> None:
    status = ApplicationStatus(args.status) if args.status else None
    records = tracker.query(status=status, min_score=args.min_score,
                            limit=args.limit)
    if config.REMOTE_ONLY and not getattr(args, "all_locations", False):
        records = [r for r in records if is_remote_listing(r.listing)]
    if not records:
        print("No matching jobs in the queue.")
        return

    print(f"{'SCORE':>6}  {'STATUS':<9}  {'JOB ID':<16}  COMPANY / TITLE")
    print("-" * 78)
    for rec in records:
        score = rec.score.fit_score if rec.score else 0.0
        flag = ""
        if rec.application and rec.application.unsupported_claims:
            flag = "  ⚠ unverified claims"
        print(f"{score:>6.1f}  {rec.status.value:<9}  {rec.listing.job_id:<16}  "
              f"{rec.listing.company} — {rec.listing.title}{flag}")


def cmd_show(args, tracker: Tracker) -> None:
    rec = tracker.get(args.job_id)
    if rec is None:
        print(f"No job with id {args.job_id}")
        sys.exit(1)

    lst, score, app = rec.listing, rec.score, rec.application
    print(f"\n{lst.title}  @  {lst.company}")
    print(f"Status: {rec.status.value}   |   {lst.location}   |   {lst.url}")
    print("=" * 70)

    if score:
        print(f"\nFIT SCORE: {score.fit_score}  "
              f"(title {score.title_score} / profile {score.profile_score})")
        print("Reasons:")
        for reason in score.reasons:
            print(f"  - {reason}")

    if app:
        print("\n--- TAILORED SUMMARY ---")
        print(app.tailored_summary)
        print("\n--- TOP REORDERED BULLETS ---")
        for bullet in app.reordered_bullets[:8]:
            print(f"  • {bullet}")
        print("\n--- ALIGNED KEYWORDS ---")
        print("  " + ", ".join(app.aligned_keywords[:20]))
        print("\n--- COVER LETTER ---")
        print(app.cover_letter)
        if app.unsupported_claims:
            print("\n⚠  UNVERIFIED CLAIMS — review before submitting:")
            for claim in app.unsupported_claims:
                print(f"  ! {claim}")
        else:
            print("\n✓ No unverified claims detected.")
    else:
        print("\n(No tailored application — score below threshold.)")
    print()


def cmd_status(args, tracker: Tracker) -> None:
    try:
        new_status = ApplicationStatus(args.new_status)
    except ValueError:
        valid = ", ".join(s.value for s in ApplicationStatus)
        print(f"Invalid status. Use one of: {valid}")
        sys.exit(1)
    if tracker.set_status(args.job_id, new_status):
        print(f"{args.job_id} -> {new_status.value}")
    else:
        print(f"No job with id {args.job_id}")
        sys.exit(1)


def cmd_stats(args, tracker: Tracker) -> None:
    stats = tracker.stats()
    if not stats:
        print("Pipeline is empty. Run 'discover' first.")
        return
    print("Pipeline state:")
    for status, count in sorted(stats.items()):
        print(f"  {status:<10} {count}")
    print(f"  {'TOTAL':<10} {sum(stats.values())}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobpipeline",
                                     description="Job application pipeline")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_disc = sub.add_parser("discover", help="run a discovery cycle")
    p_disc.add_argument("--no-tailor", action="store_true",
                        help="skip resume tailoring")
    p_disc.set_defaults(func=cmd_discover)

    p_list = sub.add_parser("list", help="show the review queue")
    p_list.add_argument("--status", choices=[s.value for s in ApplicationStatus])
    p_list.add_argument("--min-score", type=float, default=None)
    p_list.add_argument("--limit", type=int, default=50)
    p_list.add_argument(
        "--all-locations",
        action="store_true",
        help="include non-remote jobs (overrides REMOTE_ONLY in config)",
    )
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="show full detail for one job")
    p_show.add_argument("job_id")
    p_show.set_defaults(func=cmd_show)

    p_stat = sub.add_parser("status", help="set a job's status")
    p_stat.add_argument("job_id")
    p_stat.add_argument("new_status")
    p_stat.set_defaults(func=cmd_status)

    p_stats = sub.add_parser("stats", help="pipeline state summary")
    p_stats.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    with Tracker(config.DB_PATH) as tracker:
        args.func(args, tracker)


if __name__ == "__main__":
    main()
