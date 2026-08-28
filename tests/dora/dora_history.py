"""
dora_history.py

Persistent storage for DORA metrics runs, used to power historical trend
analysis. This deliberately lives in its own directory, separate from
`reports/`, because DORAFramework.cleanup_old_reports() wipes the reports
directory at the start of every run. If history were stored there, every
run would erase the very data needed to plot a trend the next time around.

Each run is written as its own timestamped JSON file:
    dora_history/<organization>/run_<YYYYMMDD_HHMMSS>.json

with the shape:
    {
        "organization": "easyjet-dev",
        "generated_at": "2026-08-16T09:00:00",
        "repository_count": 12,
        "repositories": [ ... same list DORAMetricsCalculator produces ... ]
    }

This shape matches what DORAVisualizer.create_historical_trend_chart()
already expects (a list of these dicts), so no changes were needed there.
"""
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class DORAHistoryStore:
    """Reads and writes historical DORA metrics runs to disk."""

    def __init__(self, history_dir: str = "dora_history"):
        self.history_dir = history_dir

    def _org_dir(self, organization: str) -> str:
        # Keep organizations separated so trends never mix across orgs
        safe_org = organization.replace('/', '_')
        path = os.path.join(self.history_dir, safe_org)
        os.makedirs(path, exist_ok=True)
        return path

    def save_run(self, metrics_data: List[Dict], organization: str) -> Optional[str]:
        """Persist a completed run. Returns the path written, or None on failure."""
        if not metrics_data:
            return None

        run_record = {
            'organization': organization,
            'generated_at': datetime.now().isoformat(),
            'repository_count': len(metrics_data),
            'repositories': metrics_data,
        }

        org_dir = self._org_dir(organization)
        # Second-resolution timestamp isn't unique enough for back-to-back runs
        # (tests, manual re-runs, scripted loops) - a short uuid suffix guarantees
        # no run ever silently overwrites another.
        filename = f'run_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:8]}.json'
        path = os.path.join(org_dir, filename)

        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(run_record, f, indent=2)
            return path
        except OSError as e:
            print(f"  Warning: could not write history file {path}: {e}")
            return None

    def load_history(self, organization: str, days: Optional[int] = 90) -> List[Dict]:
        """
        Load all past runs for an organization, oldest first.

        days: only keep runs newer than this many days (None = no limit).
        Malformed or unreadable files are skipped rather than raising, since
        a corrupt history file should never take down a live analysis run.
        """
        org_dir = self._org_dir(organization)
        cutoff = datetime.now() - timedelta(days=days) if days else None

        runs = []
        for filename in sorted(os.listdir(org_dir)):
            if not filename.endswith('.json'):
                continue
            path = os.path.join(org_dir, filename)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    record = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                print(
                    f"  Warning: skipping unreadable history file {filename}: {e}")
                continue

            generated_at = record.get('generated_at')
            if cutoff and generated_at:
                try:
                    run_date = datetime.fromisoformat(generated_at)
                    if run_date < cutoff:
                        continue
                except ValueError:
                    pass  # keep the record if we can't parse the date

            runs.append(record)

        return runs

    def run_count(self, organization: str) -> int:
        """Cheap check for 'do we have enough history to bother plotting a trend'."""
        org_dir = self._org_dir(organization)
        return len([f for f in os.listdir(org_dir) if f.endswith('.json')])
