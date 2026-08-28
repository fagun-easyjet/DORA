"""
dashboard_generation.py

Builds the interactive HTML report for a DORA metrics run.

This lives in its own module - separate from DORAFramework in dora_demo.py -
because the HTML/CSS/JS template is large and was previously buried in the
middle of the orchestration script, making it hard to find and edit. All the
report-assembly logic (dropdown-driven repo detail view, per-chart tooltips,
per-repo insights) lives here now; dora_demo.py just calls generate().
"""
import base64
import os
from datetime import datetime
from typing import Dict, List, Optional


# Thresholds mirror DORAMetricsCalculator._calculate_performance_level(), so
# the advice given here always lines up with why a repo landed at the tier
# it did.
_ELITE_LEAD_TIME_H = 1
_HIGH_LEAD_TIME_H = 24
_ELITE_FAILURE_RATE_PCT = 15
_HIGH_FAILURE_RATE_PCT = 30
_ELITE_RESTORE_TIME_H = 1
_HIGH_RESTORE_TIME_H = 24

# Recommendation banks, grouped by which metric they help. When generating
# insights for a repo, we look at which of its metrics are furthest from
# Elite and pull from the matching bank(s), so "Quick Wins" and "Growth
# Opportunities" are actually relevant to that specific repo's weak spots
# instead of a fixed list shown to every repo regardless of its numbers.
_QUICK_WINS_BY_METRIC = {
    'lead_time': [
        "Break large pull requests into smaller, faster-to-review chunks",
        "Add automated review reminders so PRs don't stall waiting on a reviewer",
        "Run CI checks in parallel to shrink the pipeline's critical path",
    ],
    'failure_rate': [
        "Add automated smoke tests that block a bad release before it ships",
        "Increase test coverage on the code paths that fail most often",
        "Require a green CI run before merge, if not already enforced",
    ],
    'restore_time': [
        "Set up automatic rollback when a post-deploy health check fails",
        "Write a short incident runbook so recovery doesn't depend on one person",
        "Add alerting tied directly to this repo's deploy pipeline",
    ],
    'deployment_frequency': [
        "Move toward trunk-based development to enable smaller, more frequent releases",
        "Remove manual approval steps that aren't adding real safety",
        "Ship behind feature flags so deploys and launches can be decoupled",
    ],
}

_GROWTH_OPPORTUNITIES_BY_METRIC = {
    'lead_time': [
        "Adopt trunk-based development to keep branches short-lived",
        "Invest in developer self-service tooling to remove handoff delays",
        "Set an explicit team SLA for PR review turnaround",
    ],
    'failure_rate': [
        "Introduce canary deployments to catch failures before full rollout",
        "Build a contract-testing suite for this repo's key integrations",
        "Run regular chaos/failure-injection tests against staging",
    ],
    'restore_time': [
        "Practice incident response with regular game days",
        "Invest in better observability (tracing, structured logs) for faster diagnosis",
        "Automate common remediation steps instead of handling them manually",
    ],
    'deployment_frequency': [
        "Establish a cross-team DevOps community to share what's working",
        "Build a self-service deployment platform other teams can reuse",
        "Track and publish this repo's DORA metrics so progress is visible",
    ],
}

# Tooltip text for the "Key Performance Indicators" cards in the HTML report.
# These are org-wide aggregates (unlike the per-repo insights above), so the
# wording is explicit about how each number is aggregated - e.g. "averaged
# evenly across repos" rather than weighted by activity - since that's exactly
# the kind of thing a stat like "Avg Lead Time" can otherwise be misread as.
KPI_CARD_EXPLANATIONS = {
    'avg_lead_time': "Each repository's lead time (PR opened to merged), averaged evenly across "
                      "every repo analyzed in this run. A single slow repo pulls this up just as "
                      "much regardless of how active it is - check Repository Performance Ranking "
                      "below for the per-repo breakdown.",
    'avg_failure_rate': "Each repository's change failure rate, averaged evenly across every repo "
                         "analyzed in this run - the share of GitHub Actions workflow runs that "
                         "ended in failure.",
    'performance_distribution': "How many of the repositories in this run land in each DORA tier. "
                                 "A repo only counts toward Elite or High if every one of its four "
                                 "metrics clears that tier's threshold at the same time.",
    'data_analyzed': "Total deployment events found across every repository in this run, from the "
                      "GitHub Deployments API, over the last 30 days. Repos that don't use GitHub "
                      "Deployments for releases will show 0 here even if they ship often.",
    'workflow_runs': "Total GitHub Actions workflow runs analyzed across every repository in this "
                      "run - this is the raw data Change Failure Rate and Time to Restore are "
                      "calculated from.",
    'pull_requests': "Total merged pull requests analyzed across every repository in this run - "
                      "this is the raw data Lead Time for Changes is calculated from.",
}


def generate_repo_insights(repo_name: str, metrics: Dict,
                            data_sources: Optional[Dict] = None,
                            previous_metrics: Optional[Dict] = None,
                            org_averages: Optional[Dict] = None) -> Dict[str, List[str]]:
    """
    Build "Actionable Insights & Recommendations" content for one repository,
    driven entirely by that repo's own numbers - not org-wide averages. This
    is what makes the insights section change when a different repo is picked
    from the dropdown.

    Optional context, used wherever it's actually available for this repo:
      data_sources: this repo's 'data_sources' dict, to flag when a metric's
        recommendation is based on thin or missing data.
      previous_metrics: this repo's metrics from the run before this one (if
        any), to report whether it's trending better or worse.
      org_averages: {'lead_time', 'failure_rate', 'restore_time'} averaged
        across every repo in this run, to show how this repo compares to peers.

    Returns {'optimization_focus': [...], 'quick_wins': [...],
             'growth_opportunities': [...], 'context_signals': [...]} - each a
    list of ready-to-render HTML <li> inner strings. 'context_signals' may be
    empty if none of the optional context above was available.
    """
    lead_time = metrics.get('lead_time_hours', 0)
    failure_rate = metrics.get('change_failure_rate', 0)
    restore_time = metrics.get('time_to_restore_hours', 0)
    deploy_freq = metrics.get('deployment_frequency', 'UNKNOWN')

    focus = []

    if lead_time > _HIGH_LEAD_TIME_H:
        focus.append(
            f"🚨 <strong>Critical:</strong> Lead time is {lead_time:.1f}h, above the "
            f"High threshold ({_HIGH_LEAD_TIME_H}h). Code review speed and pipeline "
            f"length are the likely bottlenecks."
        )
    elif lead_time > _ELITE_LEAD_TIME_H:
        focus.append(
            f"⚠️ <strong>Opportunity:</strong> Lead time is {lead_time:.1f}h - within "
            f"High range but above Elite ({_ELITE_LEAD_TIME_H}h)."
        )
    else:
        focus.append(f"✅ <strong>Strength:</strong> Lead time of {lead_time:.1f}h is at Elite level.")

    if failure_rate > _HIGH_FAILURE_RATE_PCT:
        focus.append(
            f"🚨 <strong>Critical:</strong> {failure_rate:.1f}% change failure rate is "
            f"above the High threshold ({_HIGH_FAILURE_RATE_PCT}%). Strengthen testing "
            f"and deployment validation before merge."
        )
    elif failure_rate > _ELITE_FAILURE_RATE_PCT:
        focus.append(
            f"⚠️ <strong>Opportunity:</strong> {failure_rate:.1f}% failure rate is within "
            f"High range but above Elite ({_ELITE_FAILURE_RATE_PCT}%)."
        )
    else:
        focus.append(f"✅ <strong>Strength:</strong> {failure_rate:.1f}% failure rate is at Elite level.")

    if restore_time > _HIGH_RESTORE_TIME_H:
        focus.append(
            f"🚨 <strong>Critical:</strong> {restore_time:.1f}h to restore service is "
            f"above the High threshold ({_HIGH_RESTORE_TIME_H}h). Faster rollback or "
            f"incident response would help most here."
        )
    elif restore_time > _ELITE_RESTORE_TIME_H:
        focus.append(
            f"⚠️ <strong>Opportunity:</strong> {restore_time:.1f}h restore time is within "
            f"High range but above Elite ({_ELITE_RESTORE_TIME_H}h)."
        )
    else:
        focus.append(f"✅ <strong>Strength:</strong> {restore_time:.1f}h restore time is at Elite level.")

    if deploy_freq == 'MONTHLY':
        focus.append(
            "📈 <strong>Goal:</strong> Deploying MONTHLY - moving to WEEKLY or DAILY "
            "releases would unlock a higher DORA tier."
        )
    elif deploy_freq == 'WEEKLY':
        focus.append(
            "📊 <strong>Monitor:</strong> WEEKLY deployments are solid; DAILY would put "
            "this repo in Elite territory."
        )
    elif deploy_freq == 'DAILY':
        focus.append("🎉 <strong>Success:</strong> DAILY deployment cadence is excellent.")
    else:
        focus.append(f"📊 <strong>Note:</strong> Deployment frequency is {deploy_freq}.")

    # Rank how far each metric is from Elite (as a ratio) so the weakest
    # metrics surface first when picking recommendations.
    bottlenecks = []
    if lead_time > _ELITE_LEAD_TIME_H:
        bottlenecks.append(('lead_time', lead_time / _ELITE_LEAD_TIME_H))
    if failure_rate > _ELITE_FAILURE_RATE_PCT:
        bottlenecks.append(('failure_rate', failure_rate / _ELITE_FAILURE_RATE_PCT))
    if restore_time > _ELITE_RESTORE_TIME_H:
        bottlenecks.append(('restore_time', restore_time / _ELITE_RESTORE_TIME_H))
    if deploy_freq != 'DAILY':
        bottlenecks.append(('deployment_frequency', {'WEEKLY': 2, 'MONTHLY': 4}.get(deploy_freq, 5)))
    bottlenecks.sort(key=lambda pair: pair[1], reverse=True)

    quick_wins: List[str] = []
    growth: List[str] = []
    for metric_name, _ in bottlenecks[:2]:  # focus on the two weakest areas
        quick_wins.extend(_QUICK_WINS_BY_METRIC[metric_name][:2])
        growth.extend(_GROWTH_OPPORTUNITIES_BY_METRIC[metric_name][:2])

    if not bottlenecks:
        # Every metric is already at Elite - shift from "fix problems" to
        # "share and sustain" advice instead of leaving the section empty.
        quick_wins = [
            "Document what's working here so other teams can copy the pattern",
            "Set up alerting to catch any regression from this level quickly",
        ]
        growth = [
            "Use this repo as a reference implementation for DORA best practices",
            "Explore progressive delivery (canaries, chaos engineering) to stay ahead",
        ]

    context_signals: List[str] = _generate_context_signals(
        repo_name, metrics, bottlenecks, data_sources, previous_metrics, org_averages
    )

    return {
        'optimization_focus': focus,
        'quick_wins': quick_wins[:5],
        'growth_opportunities': growth[:5],
        'context_signals': context_signals,
    }


def _generate_context_signals(repo_name: str, metrics: Dict, bottlenecks: List,
                               data_sources: Optional[Dict], previous_metrics: Optional[Dict],
                               org_averages: Optional[Dict]) -> List[str]:
    """
    Insights that come from *how this repo behaves* rather than just where its
    raw numbers sit against fixed thresholds: data confidence, trend versus
    its own history, how it compares to peers, and metric combinations that
    are only meaningful read together (e.g. deploying often but unreliably).
    Each check only fires when the context it needs was actually provided.
    """
    signals: List[str] = []
    lead_time = metrics.get('lead_time_hours', 0)
    failure_rate = metrics.get('change_failure_rate', 0)
    restore_time = metrics.get('time_to_restore_hours', 0)
    deploy_freq = metrics.get('deployment_frequency', 'UNKNOWN')

    # --- Data confidence: is there enough data behind these numbers? ---
    if data_sources:
        thin_metrics = []
        no_data_metrics = []
        for metric_key, info in data_sources.items():
            label = metric_key.replace('_', ' ')
            if not info.get('valid', False):
                no_data_metrics.append(label)
            elif info.get('count', 0) < 5:
                thin_metrics.append(f"{label} ({info.get('count', 0)} pts)")

        if no_data_metrics:
            signals.append(
                f"⚪ <strong>No data:</strong> {', '.join(no_data_metrics)} "
                f"{'is' if len(no_data_metrics) == 1 else 'are'} using a default value "
                f"because no real data was found - treat those figures as placeholders, not facts."
            )
        if thin_metrics:
            signals.append(
                f"🔍 <strong>Thin data:</strong> {', '.join(thin_metrics)} "
                f"{'is' if len(thin_metrics) == 1 else 'are'} based on very few data points. "
                f"Numbers may shift a lot as more runs, deploys, or PRs come in."
            )

    # --- Trend: is this repo getting better or worse over time? ---
    if previous_metrics:
        def _pct_change(current, prior):
            if prior in (0, None):
                return None
            return ((current - prior) / prior) * 100

        trend_items = [
            ('Lead time', lead_time, previous_metrics.get('lead_time_hours', 0), 'h', True),
            ('Failure rate', failure_rate, previous_metrics.get('change_failure_rate', 0), '%', True),
            ('Restore time', restore_time, previous_metrics.get('time_to_restore_hours', 0), 'h', True),
        ]
        for name, current, prior, unit, lower_is_better in trend_items:
            change = _pct_change(current, prior)
            if change is None or abs(change) < 5:
                continue  # ignore noise - only call out moves that are actually meaningful
            improved = (change < 0) if lower_is_better else (change > 0)
            icon = "📉" if improved else "📈"
            direction = "improved" if improved else "worsened"
            verdict = "Great trajectory" if improved else "Worth investigating"
            signals.append(
                f"{icon} <strong>{verdict}:</strong> {name} has {direction} by "
                f"{abs(change):.0f}% since the last collection run "
                f"({prior:.1f}{unit} → {current:.1f}{unit})."
            )

        prev_freq = previous_metrics.get('deployment_frequency')
        if prev_freq and prev_freq != deploy_freq:
            freq_rank = {'MONTHLY': 0, 'WEEKLY': 1, 'DAILY': 2}
            if freq_rank.get(deploy_freq, -1) > freq_rank.get(prev_freq, -1):
                signals.append(
                    f"📈 <strong>Great trajectory:</strong> Deployment frequency moved from "
                    f"{prev_freq} to {deploy_freq} since the last run."
                )
            elif freq_rank.get(deploy_freq, -1) < freq_rank.get(prev_freq, -1):
                signals.append(
                    f"📉 <strong>Worth investigating:</strong> Deployment frequency dropped "
                    f"from {prev_freq} to {deploy_freq} since the last run."
                )

    # --- Peer comparison: how does this repo compare to the rest of the org? ---
    if org_averages:
        def _compare(name, value, org_value, unit, lower_is_better=True):
            if not org_value:
                return None
            diff_pct = ((value - org_value) / org_value) * 100
            if abs(diff_pct) < 10:
                return None  # close enough to the pack, not worth calling out
            better = (diff_pct < 0) if lower_is_better else (diff_pct > 0)
            icon = "🏆" if better else "⚠️"
            word = "better" if better else "worse"
            return (
                f"{icon} <strong>{'Ahead of peers' if better else 'Behind peers'}:</strong> "
                f"{name} ({value:.1f}{unit}) is {abs(diff_pct):.0f}% {word} than the "
                f"org average ({org_value:.1f}{unit})."
            )

        for line in [
            _compare('Lead time', lead_time, org_averages.get('lead_time', 0), 'h'),
            _compare('Failure rate', failure_rate, org_averages.get('failure_rate', 0), '%'),
            _compare('Restore time', restore_time, org_averages.get('restore_time', 0), 'h'),
        ]:
            if line:
                signals.append(line)

    # --- Behavioral patterns: combinations that are only meaningful together ---
    if deploy_freq in ('DAILY', 'WEEKLY') and failure_rate > _HIGH_FAILURE_RATE_PCT:
        signals.append(
            f"⚠️ <strong>Risk pattern:</strong> Deploying {deploy_freq.lower()} but "
            f"{failure_rate:.1f}% of changes fail - shipping speed is outpacing safety net. "
            f"Prioritize test coverage before pushing frequency any higher."
        )
    if deploy_freq == 'MONTHLY' and failure_rate <= _ELITE_FAILURE_RATE_PCT:
        signals.append(
            f"💡 <strong>Untapped capacity:</strong> Failure rate is excellent "
            f"({failure_rate:.1f}%) but releases are only MONTHLY - reliability isn't "
            f"the constraint here, release cadence is. Safe to try shipping more often."
        )
    if lead_time <= _ELITE_LEAD_TIME_H and restore_time > _HIGH_RESTORE_TIME_H:
        signals.append(
            "⚠️ <strong>Risk pattern:</strong> Changes ship fast, but recovery from a bad "
            "one is slow - a single bad deploy could cause an extended outage. Fast-forward "
            "rollback capability would close this gap."
        )
    if failure_rate <= _ELITE_FAILURE_RATE_PCT and restore_time <= _ELITE_RESTORE_TIME_H and deploy_freq in ('DAILY', 'WEEKLY'):
        signals.append(
            "🎉 <strong>Well-rounded:</strong> Frequent deployments, low failure rate, and "
            "fast recovery together - this is the profile of a genuinely resilient pipeline."
        )

    return signals




class DashboardHTMLGenerator:
    """Builds the interactive HTML report for a DORA metrics run.

    Needs a DORAVisualizer instance only for its chart-explanation
    dictionaries (CHART_EXPLANATIONS / DASHBOARD_CHART_EXPLANATIONS) - it
    doesn't generate any charts itself, only assembles HTML around images
    that were already created elsewhere.
    """

    def __init__(self, visualizer):
        self.visualizer = visualizer

    @staticmethod
    def _compute_org_averages(repo_list: List[Dict]) -> Optional[Dict[str, float]]:
        """Average lead time / failure rate / restore time across every repo in
        this run, used so each repo's insights can say how it compares to peers.
        Returns None if there's nothing to average (shouldn't normally happen)."""
        if not repo_list:
            return None
        n = len(repo_list)
        return {
            'lead_time': sum(r['metrics'].get('lead_time_hours', 0) for r in repo_list) / n,
            'failure_rate': sum(r['metrics'].get('change_failure_rate', 0) for r in repo_list) / n,
            'restore_time': sum(r['metrics'].get('time_to_restore_hours', 0) for r in repo_list) / n,
        }

    @staticmethod
    def _previous_run_metrics_by_repo(historical_data: List[Dict],
                                       current_run_timestamp: Optional[str]) -> Dict[str, Dict]:
        """
        For each repo, find its metrics from the run immediately before the
        current one, so insights can report a trend ("lead time improved 20%
        since last run"). historical_data includes the current run itself (it's
        saved to history before the HTML is generated), so that run is
        excluded by comparing timestamps rather than assumed to be last in
        the list.
        """
        try:
            current_dt = (datetime.strptime(current_run_timestamp, "%Y%m%d_%H%M%S")
                          if current_run_timestamp else None)
        except ValueError:
            current_dt = None

        past_runs = []
        for run in historical_data:
            generated_at = run.get('generated_at')
            if not generated_at:
                continue
            try:
                run_dt = datetime.fromisoformat(generated_at)
            except ValueError:
                continue
            if current_dt and run_dt >= current_dt:
                continue  # this run is the current one (or somehow later) - not "previous"
            past_runs.append((run_dt, run))

        if not past_runs:
            return {}

        past_runs.sort(key=lambda pair: pair[0])
        _, most_recent_past_run = past_runs[-1]

        result = {}
        for repo in most_recent_past_run.get('repositories', []):
            if 'metrics' in repo:
                result[repo['repository']] = repo['metrics']
        return result

    def generate(self, metrics_data: List[Dict], organization: str, dashboard_path: str,
                 repo_chart_sets: Optional[Dict[str, Dict[str, str]]] = None,
                 dashboard_chart_set: Optional[Dict[str, str]] = None,
                 repo_composite_paths: Optional[Dict[str, str]] = None,
                 reports_dir: str = "reports", run_timestamp: Optional[str] = None,
                 historical_data: Optional[List[Dict]] = None) -> str:
        """
        Build the full interactive HTML report and write it to reports_dir.

        repo_composite_paths: {repo_name: path_to_composite_png} - the full
        2x2 image created by DORAVisualizer.create_individual_repository_report()
        for each repo, used only for the "Download Full Report" link. Passed in
        explicitly (rather than re-discovered by scanning the charts folder)
        since the caller already has these paths from the same run.

        historical_data: past run records (same shape as
        DORAHistoryStore.load_history()'s return value), used to add
        trend-vs-last-run insights per repo. Optional - without it, insights
        just skip the trend signal rather than failing.
        """
        repo_chart_sets = repo_chart_sets or {}
        dashboard_chart_set = dashboard_chart_set or {}
        repo_composite_paths = repo_composite_paths or {}
        historical_data = historical_data or []
        run_timestamp = run_timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")

        # Convert main dashboard image to base64
        try:
            with open(dashboard_path, 'rb') as img_file:
                img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
        except Exception as e:
            print(f"  Warning: Could not encode dashboard image: {e}")
            img_base64 = ""

        # Base64-encode the split dashboard chart images (one per panel), used
        # for the tooltip'd chart tiles under "Overall Performance Dashboard"
        dashboard_chart_images: Dict[str, str] = {}
        for chart_key, path in dashboard_chart_set.items():
            try:
                with open(path, 'rb') as img_file:
                    dashboard_chart_images[chart_key] = base64.b64encode(img_file.read()).decode('utf-8')
            except Exception as e:
                print(f"  Warning: Could not encode dashboard chart '{chart_key}': {e}")

        # Collect individual repository report images (composite PNG, used for
        # the "download full report" link) directly from the paths this run
        # already produced - no directory scanning needed.
        repo_images = {}
        for repo in metrics_data:
            if 'metrics' in repo:
                repo_name = repo['repository']
                composite_path = repo_composite_paths.get(repo_name)
                if composite_path:
                    try:
                        with open(composite_path, 'rb') as img_file:
                            repo_images[repo_name] = base64.b64encode(
                                img_file.read()).decode('utf-8')
                    except Exception as e:
                        print(
                            f"  Warning: Could not encode report image for {repo_name}: {e}")
                        repo_images[repo_name] = None
                else:
                    repo_images[repo_name] = None

        # Base64-encode the 4 split per-chart images per repo, used for the
        # dropdown-driven detail view where each chart gets its own tooltip
        repo_chart_images: Dict[str, Dict[str, str]] = {}
        for repo_name, chart_paths in repo_chart_sets.items():
            encoded = {}
            for chart_key, path in chart_paths.items():
                try:
                    with open(path, 'rb') as img_file:
                        encoded[chart_key] = base64.b64encode(img_file.read()).decode('utf-8')
                except Exception as e:
                    print(f"  Warning: Could not encode {chart_key} chart for {repo_name}: {e}")
            repo_chart_images[repo_name] = encoded

        # Create HTML content with TRENDING theme
        html_content = f"""<!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>📊 DORA Metrics Dashboard</title>
        <style>
            :root {{
                --primary: #6366f1;
                --primary-dark: #4f46e5;
                --secondary: #f97316;
                --success: #10b981;
                --warning: #f59e0b;
                --danger: #ef4444;
                --dark: #1e293b;
                --light: #f8fafc;
                --gradient-primary: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                --gradient-success: linear-gradient(135deg, #10b981 0%, #059669 100%);
                --gradient-warning: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
                --gradient-danger: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
            }}
            
            body {{
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
                color: var(--dark);
                line-height: 1.6;
            }}
            
            .container {{
                max-width: 1600px;
                margin: 0 auto;
                background: white;
                padding: 40px;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.08);
                border: 1px solid #e2e8f0;
            }}
            
            .header {{
                background: var(--gradient-primary);
                padding: 40px;
                border-radius: 16px;
                color: white;
                margin-bottom: 40px;
                text-align: center;
                position: relative;
                overflow: hidden;
            }}
            
            .header::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 320"><path fill="%23ffffff10" d="M0,224L48,213.3C96,203,192,181,288,181.3C384,181,480,203,576,192C672,181,768,139,864,128C960,117,1056,139,1152,149.3C1248,160,1344,160,1392,160L1440,160L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z"></path></svg>');
                background-size: cover;
                opacity: 0.1;
            }}
            
            .trending-badge {{
                display: inline-block;
                background: rgba(255,255,255,0.2);
                padding: 8px 20px;
                border-radius: 50px;
                font-size: 0.9em;
                margin-bottom: 20px;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255,255,255,0.3);
            }}
            
            .header h1 {{
                font-size: 3em;
                margin: 10px 0;
                font-weight: 800;
                text-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            
            .header h2 {{
                font-size: 1.8em;
                margin: 10px 0 20px;
                opacity: 0.95;
                font-weight: 500;
            }}
            
            .timestamp {{
                background: rgba(255,255,255,0.1);
                padding: 10px 20px;
                border-radius: 10px;
                display: inline-block;
                backdrop-filter: blur(10px);
            }}
            
            .dashboard-container {{
                background: var(--light);
                padding: 30px;
                border-radius: 16px;
                margin: 40px 0;
                border: 1px solid #e2e8f0;
            }}
            
            .dashboard-img {{
                width: 100%;
                border-radius: 12px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.08);
                transition: transform 0.3s ease;
                border: 1px solid #e2e8f0;
            }}
            
            .dashboard-img:hover {{
                transform: scale(1.01);
            }}
            
            .repo-dashboards-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(600px, 1fr));
                gap: 30px;
                margin: 40px 0;
            }}

            .repo-selector-bar {{
                display: flex;
                align-items: center;
                gap: 12px;
                margin: 20px 0 10px 0;
                flex-wrap: wrap;
            }}

            .repo-select {{
                padding: 10px 16px;
                border-radius: 10px;
                border: 1px solid #e2e8f0;
                font-size: 1em;
                font-family: inherit;
                background: white;
                color: var(--dark);
                box-shadow: 0 2px 8px rgba(0,0,0,0.04);
                min-width: 260px;
                cursor: pointer;
            }}

            .repo-details-container {{
                margin: 20px 0 40px 0;
            }}

            .chart-mini-grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 20px;
                margin-top: 10px;
            }}

            .dashboard-chart-grid {{
                grid-template-columns: repeat(3, 1fr);
            }}

            .chart-tile {{
                position: relative;
                background: #f8fafc;
                border-radius: 12px;
                padding: 15px;
                border: 1px solid #e2e8f0;
                overflow: visible;
            }}

            .chart-tile img {{
                width: 100%;
                border-radius: 8px;
                display: block;
            }}

            /* Individual Repository Reports charts are capped a bit under
            their natural render size, just to keep four tiles per repo card
            from stretching arbitrarily tall on wide screens. Scoped to
            .repo-details-container only, so the main dashboard grid above is
            unaffected. */
            .repo-details-container .chart-tile img {{
                width: auto;
                max-width: 100%;
                max-height: 400px;
                margin: 0 auto;
            }}

            .repo-details-container .chart-tile {{
                text-align: center;
            }}

            .chart-tile-title {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 8px;
                font-weight: 600;
                color: var(--dark);
                font-size: 0.95em;
            }}

            .tooltip-wrap {{
                position: relative;
                display: inline-block;
            }}

            .tooltip-icon {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 18px;
                height: 18px;
                border-radius: 50%;
                background: var(--primary);
                color: white;
                font-size: 0.75em;
                font-weight: 700;
                font-style: italic;
                cursor: help;
                user-select: none;
            }}

            .tooltip-text {{
                visibility: hidden;
                opacity: 0;
                transition: opacity 0.2s ease;
                position: absolute;
                z-index: 50;
                right: 0;
                top: 24px;
                width: 260px;
                background: var(--dark);
                color: white;
                padding: 10px 12px;
                border-radius: 8px;
                font-size: 0.8em;
                line-height: 1.4;
                font-weight: 400;
                box-shadow: 0 8px 24px rgba(0,0,0,0.2);
                pointer-events: none;
            }}

            .tooltip-wrap:hover .tooltip-text {{
                visibility: visible;
                opacity: 1;
            }}
            
            .repo-dashboard-card {{
                background: white;
                padding: 25px;
                border-radius: 16px;
                box-shadow: 0 5px 20px rgba(0,0,0,0.05);
                border: 1px solid #e2e8f0;
                transition: transform 0.3s ease, box-shadow 0.3s ease;
            }}
            
            .repo-dashboard-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 15px 40px rgba(0,0,0,0.1);
            }}
            
            .repo-header {{
                display: flex;
                align-items: center;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 2px solid #f1f5f9;
            }}
            
            .repo-icon {{
                width: 50px;
                height: 50px;
                border-radius: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-right: 15px;
                font-size: 1.5em;
                color: white;
                background: var(--gradient-primary);
            }}
            
            .metrics-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 25px;
                margin: 40px 0;
            }}
            
            .metric-card {{
                background: white;
                padding: 30px;
                border-radius: 16px;
                box-shadow: 0 5px 20px rgba(0,0,0,0.05);
                border: 1px solid #e2e8f0;
                transition: transform 0.3s ease, box-shadow 0.3s ease;
            }}
            
            .metric-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 15px 40px rgba(0,0,0,0.1);
            }}
            
            .metric-header {{
                display: flex;
                align-items: center;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 2px solid #f1f5f9;
            }}
            
            .metric-icon {{
                width: 50px;
                height: 50px;
                border-radius: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-right: 15px;
                font-size: 1.5em;
                color: white;
            }}
            
            .metric-value {{
                font-size: 2.5em;
                font-weight: 800;
                margin: 10px 0;
                background: var(--gradient-primary);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            
            .metric-label {{
                color: #64748b;
                font-size: 0.9em;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-top: 5px;
            }}
            
            .performance-badge {{
                padding: 8px 20px;
                border-radius: 50px;
                font-weight: 700;
                font-size: 0.9em;
                display: inline-flex;
                align-items: center;
                gap: 8px;
            }}
            
            .elite {{
                background: var(--gradient-success);
                color: white;
                box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3);
            }}
            
            .high {{
                background: var(--gradient-warning);
                color: white;
                box-shadow: 0 4px 15px rgba(245, 158, 11, 0.3);
            }}
            
            .low {{
                background: var(--gradient-danger);
                color: white;
                box-shadow: 0 4px 15px rgba(239, 68, 68, 0.3);
            }}
            
            .trending-list {{
                background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
                padding: 30px;
                border-radius: 16px;
                margin: 40px 0;
                border: 1px solid #e2e8f0;
            }}
            
            .trending-item {{
                display: flex;
                align-items: center;
                padding: 20px;
                background: white;
                margin: 15px 0;
                border-radius: 12px;
                border-left: 4px solid var(--primary);
                transition: transform 0.2s ease;
            }}
            
            .trending-item:hover {{
                transform: translateX(5px);
                border-left-color: var(--secondary);
            }}
            
            .trending-rank {{
                font-size: 1.8em;
                font-weight: 800;
                color: var(--primary);
                margin-right: 20px;
                min-width: 50px;
            }}
            
            .insights-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
                gap: 25px;
                margin: 40px 0;
            }}
            
            .insight-card {{
                background: white;
                padding: 30px;
                border-radius: 16px;
                border-top: 4px solid var(--secondary);
                box-shadow: 0 5px 20px rgba(0,0,0,0.05);
            }}
            
            .insight-card h4 {{
                color: var(--secondary);
                margin: 0 0 20px 0;
                font-size: 1.2em;
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            
            .tech-stack {{
                display: flex;
                gap: 15px;
                flex-wrap: wrap;
                margin-top: 20px;
            }}
            
            .tech-tag {{
                background: var(--light);
                padding: 8px 16px;
                border-radius: 50px;
                font-size: 0.9em;
                color: var(--primary);
                border: 1px solid #e2e8f0;
            }}

            .dashboard-repo-list {{
                display: flex;
                gap: 8px;
                flex-wrap: wrap;
                margin: 0 0 20px 0;
            }}

            .repo-chip {{
                background: #f8fafc;
                padding: 5px 12px;
                border-radius: 50px;
                font-size: 0.8em;
                color: var(--dark);
                border: 1px solid #e2e8f0;
                white-space: nowrap;
            }}
            
            .footer {{
                text-align: center;
                margin-top: 60px;
                padding-top: 40px;
                border-top: 2px solid #f1f5f9;
                color: #64748b;
            }}
            
            .section-header {{
                display: flex;
                align-items: center;
                margin: 40px 0 20px 0;
                padding-bottom: 10px;
                border-bottom: 2px solid #e2e8f0;
            }}
            
            .section-header h3 {{
                margin: 0;
                color: var(--dark);
                font-size: 1.5em;
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            
            @media (max-width: 768px) {{
                .container {{
                    padding: 20px;
                }}
                .header {{
                    padding: 30px 20px;
                }}
                .header h1 {{
                    font-size: 2em;
                }}
                .metrics-grid {{
                    grid-template-columns: 1fr;
                }}
                .repo-dashboards-grid {{
                    grid-template-columns: 1fr;
                }}
                .chart-mini-grid {{
                    grid-template-columns: 1fr;
                }}
                .repo-select {{
                    width: 100%;
                    min-width: 0;
                }}
                .tooltip-text {{
                    width: 200px;
                    right: -20px;
                }}
            }}
            
            /* Modal styles for image zoom */
            .modal {{
                display: none;
                position: fixed;
                z-index: 1000;
                padding-top: 60px;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0,0,0,0.9);
            }}
            
            .modal-content {{
                margin: auto;
                display: block;
                width: 80%;
                max-width: 1200px;
                border-radius: 10px;
            }}
            
            .close {{
                position: absolute;
                top: 20px;
                right: 35px;
                color: #f1f1f1;
                font-size: 40px;
                font-weight: bold;
                cursor: pointer;
            }}
            
            .close:hover {{
                color: #bbb;
            }}
            
            .download-btn {{
                display: inline-block;
                background: var(--gradient-primary);
                color: white;
                padding: 10px 20px;
                border-radius: 8px;
                text-decoration: none;
                margin-top: 15px;
                font-weight: 600;
                transition: transform 0.2s ease;
            }}
            
            .download-btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(99, 102, 241, 0.4);
            }}
            
            .zoom-icon {{
                position: absolute;
                top: 20px;
                right: 20px;
                background: rgba(255,255,255,0.9);
                padding: 8px;
                border-radius: 50%;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                width: 40px;
                height: 40px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            
            .zoom-icon:hover {{
                background: white;
                transform: scale(1.1);
            }}
            
            .image-container {{
                position: relative;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Header -->
            <div class="header">
                <div class="trending-badge">🚀 TRENDS ANALYSIS & INSIGHTS</div>
                <h1>DORA Framework: Key Metrics and Best Practices</h1>
                <h3>Organizations: {organization}</h3>
                <div class="timestamp">
                    📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </div>
                <div style="margin-top: 20px; font-size: 0.9em; opacity: 0.9;">
                    📊 {len(metrics_data)} repositories analyzed • 
                    ⚡ Real-time Metrics • 
                    🎯 Performance Insights
                </div>
            </div>
            
            <!-- Main Dashboard -->
            <div class="section-header">
                <h3>📈 Overall Performance Dashboard</h3>
            </div>

            <div class="dashboard-repo-list">
    """

        dashboard_repo_names = [repo['repository'] for repo in metrics_data if 'metrics' in repo]
        html_content += f'<span style="font-size: 0.85em; color: #64748b; margin-right: 4px; align-self: center;">Repositories in this view ({len(dashboard_repo_names)}):</span>'
        for repo_name in dashboard_repo_names:
            html_content += f'<span class="repo-chip">{repo_name}</span>'

        html_content += """
            </div>
            
            <div class="dashboard-container">
    """

        dashboard_chart_titles = {
            'performance_distribution': 'Performance Level Distribution',
            'deployment_frequency': 'Deployment Frequency Distribution',
            'lead_time': 'Lead Time for Changes',
            'failure_rate': 'Change Failure Rate',
            'time_to_restore': 'Time to Restore Service',
            'correlation_heatmap': 'Metrics Correlation Heatmap',
            'trend_lead_time': 'Lead Time Trend by Repo',
            'trend_failure_rate': 'Failure Rate Trend by Repo',
            'trend_restore_time': 'Restore Time Trend by Repo',
        }
        dashboard_chart_order = list(dashboard_chart_titles.keys())

        if dashboard_chart_images:
            html_content += """
                <div class="chart-mini-grid dashboard-chart-grid">
    """
            for chart_key in dashboard_chart_order:
                b64 = dashboard_chart_images.get(chart_key)
                if not b64:
                    continue
                title = dashboard_chart_titles[chart_key]
                explanation = self.visualizer.DASHBOARD_CHART_EXPLANATIONS.get(chart_key, '')
                img_id = f"dashChart_{chart_key}"
                html_content += f"""
                    <div class="chart-tile">
                        <div class="chart-tile-title">
                            <span>{title}</span>
                            <span class="tooltip-wrap">
                                <span class="tooltip-icon">i</span>
                                <span class="tooltip-text">{explanation}</span>
                            </span>
                        </div>
                        <img src="data:image/png;base64,{b64}" alt="{title}"
                            id="{img_id}" style="cursor: zoom-in;" onclick="openModal('{img_id}')">
                    </div>
    """
            html_content += """
                </div>
    """
        elif img_base64:
            # Fallback: split images weren't available for some reason - still
            # show the composite so the report isn't empty
            html_content += f"""
                <div class="image-container">
                    <img class="dashboard-img" src="data:image/png;base64,{img_base64}" 
                        alt="DORA Metrics Dashboard" id="mainDashboard">
                    <div class="zoom-icon" onclick="openModal('mainDashboard')">
                        🔍
                    </div>
                </div>
    """

        if img_base64:
            html_content += f"""
                <a href="data:image/png;base64,{img_base64}" download="dora_main_dashboard.png" 
                class="download-btn" style="margin-top: 15px;">📥 Download Full Dashboard</a>
    """

        html_content += f"""
            </div>
            
        """

        html_content += f"""
            
            <!-- Key Metrics Grid -->
            <div class="section-header">
                <h3>🔑 Key Performance Indicators</h3>
            </div>
            
            <div class="metrics-grid">
                <!-- Calculate averages for overview -->
    """

        # Calculate average metrics
        avg_metrics = {
            'lead_time': 0,
            'failure_rate': 0,
            'restore_time': 0,
            'elite_count': 0,
            'high_count': 0,
            'low_count': 0,
            'total_deployments': 0,
            'total_workflow_runs': 0,
            'total_prs': 0
        }

        for repo in metrics_data:
            if 'metrics' in repo:
                metrics = repo['metrics']
                avg_metrics['lead_time'] += metrics['lead_time_hours']
                avg_metrics['failure_rate'] += metrics['change_failure_rate']
                avg_metrics['restore_time'] += metrics['time_to_restore_hours']

                perf = metrics['performance_level'].lower()
                if perf == 'elite':
                    avg_metrics['elite_count'] += 1
                elif perf == 'high':
                    avg_metrics['high_count'] += 1
                else:
                    avg_metrics['low_count'] += 1

                # Sum data points
                data_points = repo.get('data_points', {})
                avg_metrics['total_deployments'] += data_points.get(
                    'deployments_analyzed', 0)
                avg_metrics['total_workflow_runs'] += data_points.get(
                    'workflow_runs_analyzed', 0)
                avg_metrics['total_prs'] += data_points.get(
                    'pull_requests_analyzed', 0)

        repo_count = len([r for r in metrics_data if 'metrics' in r])
        if repo_count > 0:
            avg_metrics['lead_time'] /= repo_count
            avg_metrics['failure_rate'] /= repo_count
            avg_metrics['restore_time'] /= repo_count

        html_content += f"""
                <div class="metric-card">
                    <div class="metric-header">
                        <div class="metric-icon" style="background: var(--gradient-success);">⚡</div>
                        <div>
                            <h4 style="margin: 0;">Avg Lead Time</h4>
                            <div class="metric-label">Hours from commit to deploy</div>
                        </div>
                        <span class="tooltip-wrap" style="margin-left: auto;">
                            <span class="tooltip-icon">i</span>
                            <span class="tooltip-text">{KPI_CARD_EXPLANATIONS['avg_lead_time']}</span>
                        </span>
                    </div>
                    <div class="metric-value">{avg_metrics['lead_time']:.1f}h</div>
                    <div class="tech-stack">
                        <span class="tech-tag">{'🚀 Elite' if avg_metrics['lead_time'] < 1 else '⚡ Fast' if avg_metrics['lead_time'] < 24 else '🐢 Needs Improvement'}</span>
                    </div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-header">
                        <div class="metric-icon" style="background: var(--gradient-danger);">🛡️</div>
                        <div>
                            <h4 style="margin: 0;">Avg Failure Rate</h4>
                            <div class="metric-label">Failed deployments %</div>
                        </div>
                        <span class="tooltip-wrap" style="margin-left: auto;">
                            <span class="tooltip-icon">i</span>
                            <span class="tooltip-text">{KPI_CARD_EXPLANATIONS['avg_failure_rate']}</span>
                        </span>
                    </div>
                    <div class="metric-value">{avg_metrics['failure_rate']:.1f}%</div>
                    <div class="tech-stack">
                        <span class="tech-tag">{'✅ Stable' if avg_metrics['failure_rate'] < 15 else '⚠️ Moderate' if avg_metrics['failure_rate'] < 30 else '🚨 High Risk'}</span>
                    </div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-header">
                        <div class="metric-icon" style="background: var(--gradient-primary);">🔧</div>
                        <div>
                            <h4 style="margin: 0;">Performance Distribution</h4>
                            <div class="metric-label">{repo_count} repositories analyzed</div>
                        </div>
                        <span class="tooltip-wrap" style="margin-left: auto;">
                            <span class="tooltip-icon">i</span>
                            <span class="tooltip-text">{KPI_CARD_EXPLANATIONS['performance_distribution']}</span>
                        </span>
                    </div>
                    <div class="metric-value">{avg_metrics['elite_count']}/{repo_count}</div>
                    <div class="tech-stack">
                        <span class="tech-tag elite" style="padding: 4px 12px; font-size: 0.8em;">Elite: {avg_metrics['elite_count']}</span>
                        <span class="tech-tag high" style="padding: 4px 12px; font-size: 0.8em;">High: {avg_metrics['high_count']}</span>
                        <span class="tech-tag low" style="padding: 4px 12px; font-size: 0.8em;">Low: {avg_metrics['low_count']}</span>
                    </div>
                </div>
            </div>
            
            <!-- Data Statistics -->
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-header">
                        <div class="metric-icon" style="background: var(--gradient-warning);">📊</div>
                        <div>
                            <h4 style="margin: 0;">Data Analyzed</h4>
                            <div class="metric-label">Last 30 days</div>
                        </div>
                        <span class="tooltip-wrap" style="margin-left: auto;">
                            <span class="tooltip-icon">i</span>
                            <span class="tooltip-text">{KPI_CARD_EXPLANATIONS['data_analyzed']}</span>
                        </span>
                    </div>
                    <div class="metric-value">{avg_metrics['total_deployments']}</div>
                    <div class="metric-label">Deployments Tracked</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-header">
                        <div class="metric-icon" style="background: var(--gradient-primary);">⚙️</div>
                        <div>
                            <h4 style="margin: 0;">Workflow Runs</h4>
                            <div class="metric-label">CI/CD executions</div>
                        </div>
                        <span class="tooltip-wrap" style="margin-left: auto;">
                            <span class="tooltip-icon">i</span>
                            <span class="tooltip-text">{KPI_CARD_EXPLANATIONS['workflow_runs']}</span>
                        </span>
                    </div>
                    <div class="metric-value">{avg_metrics['total_workflow_runs']}</div>
                    <div class="metric-label">Runs Analyzed</div>
                </div>
                
                <div class="metric-card">
                    <div class="metric-header">
                        <div class="metric-icon" style="background: var(--gradient-success);">🔀</div>
                        <div>
                            <h4 style="margin: 0;">Pull Requests</h4>
                            <div class="metric-label">Code changes</div>
                        </div>
                        <span class="tooltip-wrap" style="margin-left: auto;">
                            <span class="tooltip-icon">i</span>
                            <span class="tooltip-text">{KPI_CARD_EXPLANATIONS['pull_requests']}</span>
                        </span>
                    </div>
                    <div class="metric-value">{avg_metrics['total_prs']}</div>
                    <div class="metric-label">PRs Analyzed</div>
                </div>
            </div>
            
            <!-- Repository Ranking -->
            <div class="trending-list">
                <h3 style="color: var(--dark); font-size: 1.5em; margin: 0 0 30px 0;">
                    📊 Repository Performance Ranking
                </h3>
    """

        # Sort repositories by performance (elite first, then high, then low)
        sorted_repos = sorted(
            [r for r in metrics_data if 'metrics' in r],
            key=lambda x: {
                'elite': 0,
                'high': 1,
                'low': 2
            }[x['metrics']['performance_level'].lower()]
        )

        for i, repo in enumerate(sorted_repos, 1):
            metrics = repo['metrics']
            perf_class = metrics['performance_level'].lower()
            data_points = repo.get('data_points', {})

            # Determine trend indicator
            trend_icon = "📈" if perf_class == 'elite' else "📊" if perf_class == 'high' else "📉"

            html_content += f"""
                <div class="trending-item">
                    <div class="trending-rank">#{i:02d}</div>
                    <div style="flex: 1;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <h4 style="margin: 0; color: var(--dark);">{repo['repository']}</h4>
                            <span class="performance-badge {perf_class}">
                                {trend_icon} {metrics['performance_level']}
                            </span>
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-top: 15px;">
                            <div>
                                <div style="font-size: 0.9em; color: #64748b;">Deployments</div>
                                <div style="font-weight: 700; font-size: 1.2em;">{metrics['deployment_frequency']}</div>
                            </div>
                            <div>
                                <div style="font-size: 0.9em; color: #64748b;">Lead Time</div>
                                <div style="font-weight: 700; font-size: 1.2em;">{metrics['lead_time_hours']:.1f}h</div>
                            </div>
                            <div>
                                <div style="font-size: 0.9em; color: #64748b;">Failure Rate</div>
                                <div style="font-weight: 700; font-size: 1.2em;">{metrics['change_failure_rate']:.1f}%</div>
                            </div>
                            <div>
                                <div style="font-size: 0.9em; color: #64748b;">Restore Time</div>
                                <div style="font-weight: 700; font-size: 1.2em;">{metrics['time_to_restore_hours']:.1f}h</div>
                            </div>
                        </div>
                        <div style="margin-top: 10px; font-size: 0.8em; color: #94a3b8;">
                            📊 Data points: {data_points.get('deployments_analyzed', 0)} deployments • 
                            {data_points.get('workflow_runs_analyzed', 0)} workflow runs • 
                            {data_points.get('pull_requests_analyzed', 0)} PRs
                        </div>
                    </div>
                </div>
    """

        html_content += """
            </div>
        """

        html_content += f"""
            <!-- Individual Repository Dashboards -->
            <div class="section-header">
                <h3>🏢 Individual Repository Reports</h3>
            </div>

            <div class="repo-selector-bar">
                <label for="repoSelector" style="font-weight: 600; color: var(--dark);">Select repository:</label>
                <select id="repoSelector" class="repo-select" onchange="showRepoDetail(this.value)">
    """

        repo_list = [repo for repo in metrics_data if 'metrics' in repo]
        for i, repo in enumerate(repo_list):
            html_content += f"""
                    <option value="repo-detail-{i}">{repo['repository']} ({repo['metrics']['performance_level']})</option>
    """

        html_content += """
                </select>
            </div>

            <div class="repo-details-container">
    """

        # Context needed for the "Context & Behavior Signals" insights card:
        # org-wide averages (for peer comparison) and, per repo, its metrics
        # from the run immediately before this one (for trend comparison).
        org_averages = self._compute_org_averages(repo_list)
        previous_metrics_by_repo = self._previous_run_metrics_by_repo(historical_data, run_timestamp)

        chart_titles = {
            'gauge': 'Performance Gauge',
            'radar': 'Metrics Radar',
            'comparison': 'Comparison with DORA Standards',
            'data_sources': 'Data Sources & Confidence',
        }

        # Add individual repository dashboards (all rendered up front; the
        # dropdown just toggles which one is visible - no server round trip)
        for i, repo in enumerate(repo_list):
            repo_name = repo['repository']
            metrics = repo['metrics']
            perf_class = metrics['performance_level'].lower()
            chart_images = repo_chart_images.get(repo_name, {})
            active_style = "block" if i == 0 else "none"

            html_content += f"""
                <div class="repo-detail" id="repo-detail-{i}" style="display: {active_style};">
                <div class="repo-dashboard-card">
                    <div class="repo-header">
                        <div class="repo-icon">
                            {i+1}
                        </div>
                        <div style="flex: 1;">
                            <h3 style="margin: 0; color: var(--dark);">{repo_name}</h3>
                            <div style="display: flex; align-items: center; gap: 15px; margin-top: 5px;">
                                <span class="performance-badge {perf_class}">
                                    {'🚀' if perf_class == 'elite' else '⚡' if perf_class == 'high' else '📊'} 
                                    {metrics['performance_level']}
                                </span>
                                <span style="font-size: 0.9em; color: #64748b;">
                                    📅 Updated: {datetime.now().strftime('%Y-%m-%d')}
                                </span>
                            </div>
                        </div>
                    </div>
                    
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin-bottom: 20px;">
                        <div style="background: #f8fafc; padding: 15px; border-radius: 10px;">
                            <div style="font-size: 0.9em; color: #64748b;">Deployment Frequency</div>
                            <div style="font-size: 1.5em; font-weight: 700; color: var(--primary);">
                                {metrics['deployment_frequency']}
                            </div>
                        </div>
                        <div style="background: #f8fafc; padding: 15px; border-radius: 10px;">
                            <div style="font-size: 0.9em; color: #64748b;">Lead Time</div>
                            <div style="font-size: 1.5em; font-weight: 700; color: var(--primary);">
                                {metrics['lead_time_hours']:.1f}h
                            </div>
                        </div>
                        <div style="background: #f8fafc; padding: 15px; border-radius: 10px;">
                            <div style="font-size: 0.9em; color: #64748b;">Failure Rate</div>
                            <div style="font-size: 1.5em; font-weight: 700; color: var(--primary);">
                                {metrics['change_failure_rate']:.1f}%
                            </div>
                        </div>
                        <div style="background: #f8fafc; padding: 15px; border-radius: 10px;">
                            <div style="font-size: 0.9em; color: #64748b;">Restore Time</div>
                            <div style="font-size: 1.5em; font-weight: 700; color: var(--primary);">
                                {metrics['time_to_restore_hours']:.1f}h
                            </div>
                        </div>
                    </div>
    """

            if chart_images:
                html_content += """
                    <div class="chart-mini-grid">
    """
                for chart_key in ['gauge', 'radar', 'comparison', 'data_sources']:
                    b64 = chart_images.get(chart_key)
                    if not b64:
                        continue
                    title = chart_titles[chart_key]
                    explanation = self.visualizer.CHART_EXPLANATIONS[chart_key]
                    img_id = f"repoChart_{i}_{chart_key}"
                    html_content += f"""
                        <div class="chart-tile">
                            <div class="chart-tile-title">
                                <span>{title}</span>
                                <span class="tooltip-wrap">
                                    <span class="tooltip-icon">i</span>
                                    <span class="tooltip-text">{explanation}</span>
                                </span>
                            </div>
                            <img src="data:image/png;base64,{b64}" alt="{title} - {repo_name}"
                                id="{img_id}" style="cursor: zoom-in;" onclick="openModal('{img_id}')">
                        </div>
    """
                html_content += """
                    </div>
    """
            else:
                html_content += """
                    <div style="background: #f1f5f9; padding: 40px; border-radius: 10px; text-align: center;">
                        <div style="font-size: 1.2em; color: #64748b; margin-bottom: 10px;">
                            📊 Individual charts not available
                        </div>
                        <div style="font-size: 0.9em; color: #94a3b8;">
                            The detailed charts for this repository could not be loaded.
                        </div>
                    </div>
    """

            # Dynamic, per-repo insights - recomputed for whichever repo this
            # card belongs to, so switching the dropdown switches the advice too.
            # Extra context (data confidence, trend vs last run, peer comparison)
            # is used wherever it's actually available for this repo.
            repo_insights = generate_repo_insights(
                repo_name, metrics,
                data_sources=repo.get('data_sources'),
                previous_metrics=previous_metrics_by_repo.get(repo_name),
                org_averages=org_averages,
            )
            html_content += """
                    <div class="section-header" style="margin: 30px 0 15px 0;">
                        <h3 style="font-size: 1.2em;">💡 Actionable Insights & Recommendations</h3>
                    </div>
                    <div class="insights-grid">
    """
            insight_sections = [
                ('🎯 Optimization Focus', repo_insights['optimization_focus']),
                ('🚀 Quick Wins', repo_insights['quick_wins']),
                ('📈 Growth Opportunities', repo_insights['growth_opportunities']),
            ]
            # Context & Behavior Signals only renders when at least one signal
            # actually fired (some repos won't have previous-run or org-average
            # context, e.g. the very first run for an org) - an empty card would
            # just be noise.
            if repo_insights['context_signals']:
                insight_sections.append(('📡 Context & Behavior Signals', repo_insights['context_signals']))

            for section_title, items in insight_sections:
                html_content += f"""
                        <div class="insight-card">
                            <h4>{section_title}</h4>
                            <ul style="margin: 0; padding-left: 20px; color: #475569;">
    """
                for item in items:
                    html_content += f'<li>{item}</li>'
                html_content += """
                            </ul>
                        </div>
    """
            html_content += """
                    </div>
    """

            img_base64_repo = repo_images.get(repo_name)
            if img_base64_repo:
                html_content += f"""
                    <a href="data:image/png;base64,{img_base64_repo}" download="dora_report_{repo_name}.png" 
                    class="download-btn" style="margin-top: 15px;">📥 Download {repo_name} Full Report</a>
    """

            html_content += """
                </div>
                </div>
    """

        html_content += """
            </div>
    """
        html_content += """
            <!-- Footer -->
            <div class="footer">
                <p style="font-size: 1.1em; margin-bottom: 10px;">
                    <strong>DORA Framework v2.0</strong> • DevOps Research and Assessment
                </p>
                <p style="font-size: 0.9em; color: #94a3b8;">
                    📊 Measuring what matters in DevOps performance • 
                    🔄 Data updated in real-time • 
                    🎯 Focus on continuous improvement
                </p>
                <div class="tech-stack" style="justify-content: center; margin-top: 20px;">
                    <span class="tech-tag">DevOps</span>
                    <span class="tech-tag">CI/CD</span>
                    <span class="tech-tag">GitHub Analytics</span>
                    <span class="tech-tag">Performance Metrics</span>
                    <span class="tech-tag">Engineering Excellence</span>
                </div>
            </div>
        </div>
        
        <!-- Modal for image zoom -->
        <div id="imageModal" class="modal">
            <span class="close" onclick="closeModal()">&times;</span>
            <img class="modal-content" id="modalImage">
        </div>
        
        <script>
            // Repository dropdown: show only the selected repo's detail card
            function showRepoDetail(detailId) {{
                var details = document.querySelectorAll('.repo-detail');
                details.forEach(function(el) {{
                    el.style.display = (el.id === detailId) ? 'block' : 'none';
                }});
            }}

            // Modal functionality
            function openModal(imageId) {{
                var modal = document.getElementById("imageModal");
                var modalImg = document.getElementById("modalImage");
                var img = document.getElementById(imageId);
                
                modal.style.display = "block";
                modalImg.src = img.src;
                
                // Close on click outside
                modal.onclick = function(event) {{
                    if (event.target === modal) {{
                        closeModal();
                    }}
                }}
            }}
            
            function closeModal() {{
                document.getElementById("imageModal").style.display = "none";
            }}
            
            // Add hover effects to cards
            document.addEventListener('DOMContentLoaded', function() {{
                const cards = document.querySelectorAll('.metric-card, .trending-item, .insight-card, .repo-dashboard-card');
                cards.forEach(card => {{
                    card.addEventListener('mouseenter', function() {{
                        this.style.cursor = 'pointer';
                    }});
                }});
                
                // Update timestamp on page
                function updateTime() {{
                    const now = new Date();
                    const timestampElement = document.querySelector('.timestamp');
                    if (timestampElement) {{
                        const formattedDate = now.toISOString().replace('T', ' ').substring(0, 19);
                        timestampElement.innerHTML = '📅 Generated: ' + formattedDate;
                    }}
                }}
                
                // Simulate live updates every 30 seconds
                setInterval(updateTime, 30000);
                
                // Add download all functionality
                const downloadAllBtn = document.createElement('a');
                downloadAllBtn.href = '#';
                downloadAllBtn.innerHTML = '📦 Download All Reports';
                downloadAllBtn.className = 'download-btn';
                downloadAllBtn.style.marginLeft = '20px';
                downloadAllBtn.onclick = function(e) {{
                    e.preventDefault();
                    alert('This would download all individual reports as a ZIP file in a production environment.');
                }};
                
                const dashboardHeader = document.querySelector('.section-header h3');
                if (dashboardHeader) {{
                    dashboardHeader.parentElement.appendChild(downloadAllBtn);
                }}
            }});
            
            // Keyboard shortcuts
            document.addEventListener('keydown', function(e) {{
                if (e.key === 'Escape') {{
                    closeModal();
                }}
                if (e.key === 'z' && (e.ctrlKey || e.metaKey)) {{
                    // Ctrl/Cmd + Z to zoom last image
                    const images = document.querySelectorAll('.dashboard-img');
                    if (images.length > 0) {{
                        openModal(images[images.length - 1].id);
                    }}
                }}
            }});
        </script>
    </body>
    </html>"""

        # Save HTML with proper encoding
        html_path = os.path.join(reports_dir, f'dora_report_{organization}_{run_timestamp}.html')

        try:
            # Try UTF-8 first
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
        except UnicodeEncodeError:
            # Fallback to ASCII with errors ignored
            with open(html_path, 'w', encoding='ascii', errors='ignore') as f:
                f.write(html_content)
            print("  Note: Some characters were omitted for Windows compatibility")

        print(
            f"  Created trending dashboard report: {os.path.basename(html_path)}")
        return html_path