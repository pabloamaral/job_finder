# Automated Job Application Pipeline

Reduces the manual effort of a technical job search by continuously
discovering relevant roles, scoring them for fit, and producing tailored
application materials. Discovery, filtering, and document tailoring are
automated; **final submission stays human-in-the-loop** — the tool stages
each application for review rather than submitting blindly.

## Status

This is a working scaffold. The five modules below all run and are covered
by tests. It's intentionally built so you can extend each module
independently in Claude Code without reworking the others.

## Architecture

```
sources/ ──▶ scorer ──▶ tailor ──▶ tracker ──▶ cli (review queue)
   │           │          │          │
discover    rank vs    reorder    SQLite
listings    cluster    bullets,   persistence,
            + profile  flag       dedup, status
                       unsupported
                       claims
```

| Module | File | Responsibility |
|---|---|---|
| Models | `jobpipeline/models.py` | Shared dataclasses: `JobListing`, `ScoreResult`, `TailoredApplication`, `PipelineRecord` |
| Sources | `jobpipeline/sources/` | Greenhouse, Lever, Ashby, Remotive, CSV import |
| Scorer | `jobpipeline/scorer.py` | Role-cluster title matching + owner-profile JD overlap → 0-100 fit score |
| Tailor | `jobpipeline/tailor.py` | Reorders/reweights resume bullets, aligns keywords, drafts a cover letter, **flags unsupported claims** |
| Tracker | `jobpipeline/tracker.py` | SQLite store; dedup so jobs aren't re-surfaced; status tracking |
| Pipeline | `jobpipeline/pipeline.py` | Orchestrates one discovery run |
| CLI | `jobpipeline/cli.py` | The human-in-the-loop review queue |

## Setup

```bash
pip install -r requirements.txt
```

Then edit `jobpipeline/config.py`:
- Add company board slugs to `GREENHOUSE_COMPANIES`, `LEVER_COMPANIES`, `ASHBY_COMPANIES`
- Enable `REMOTIVE_ENABLED` for the Remotive aggregator, or paste jobs into `data/import_jobs.csv`
- Tune `ROLE_CLUSTER`, `OWNER_PROFILE`, `REMOTE_ONLY`, and `SCORING` weights as needed

Find a board slug from a careers URL:

```bash
python scripts/detect_board.py --probe https://jobs.ashbyhq.com/notion
```

## Usage

```bash
python -m jobpipeline.cli discover            # pull, score, tailor, persist
python -m jobpipeline.cli list                # the review queue
python -m jobpipeline.cli list --status new --min-score 70
python -m jobpipeline.cli show <job_id>       # full detail + tailored docs
python -m jobpipeline.cli status <job_id> applied
python -m jobpipeline.cli stats               # pipeline state summary
```

Run `discover` on a schedule (cron, a loop, or GitHub Actions). Each run is
idempotent — previously seen jobs are skipped.

## Design guarantees

**Role cluster, not exact strings.** The matcher normalizes titles (`Sr.`,
`II`, separators) and matches on signal tokens, so inconsistently-named
roles ("Technical Solutions Specialist") still match the cluster.

**Resume tailoring never invents experience.** `tailor.py` only *reorders*
existing bullets — every tailored bullet is verbatim from the base resume.
`align_keywords` returns only the intersection of JD and resume vocabulary,
never keywords the JD wants but the resume lacks. `verify_claims` is a
safety net that flags any experiential claim whose terms aren't grounded in
the base resume; flags surface loudly in the review queue.

## Tests

```bash
python -m pytest tests/ -q
```

12 tests cover title-cluster logic, scoring, and the tailor's honesty
guarantees (verbatim bullets, intersection-only keywords, fabrication
detection).

## Suggested next steps in Claude Code

- **Smarter scoring** — swap token overlap in `scorer.py` for embeddings
  (`sentence-transformers`). The `ScoreResult` interface stays the same.
- **LLM cover letters** — replace the template in `tailor.generate_cover_letter`
  with an Anthropic API call. Keep `verify_claims` running on the output.
- **Rendered resume** — generate a real `.docx`/`.pdf` from the reordered
  bullets (`python-docx`) and set `TailoredApplication.resume_path`.
- **Web dashboard** — build a Flask/Textual UI on the existing `Tracker`
  queries; add the "one-click submit" staging affordance.
- **More sources** — Ashby, Remotive, and CSV import are included; add more aggregators against `JobSource`.
- **Scheduling** — wrap `pipeline.run_discovery` in a GitHub Actions cron.

## Project layout

```
job_pipeline/
├── jobpipeline/
│   ├── __init__.py
│   ├── config.py          # role cluster, owner profile, company slugs
│   ├── models.py          # shared dataclasses
│   ├── scorer.py          # filter + score
│   ├── tailor.py          # resume tailoring + claim verification
│   ├── tracker.py         # SQLite persistence
│   ├── pipeline.py        # orchestrator
│   ├── cli.py             # review queue
│   └── sources/
│       ├── base.py        # JobSource interface
│       ├── greenhouse.py
│       └── lever.py
├── resume/
│   └── base_resume.json   # structured base resume
├── tests/
│   └── test_pipeline.py
├── data/                  # SQLite db + generated apps (created at runtime)
└── requirements.txt
```
