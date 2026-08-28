from datetime import datetime, timedelta
import json
import os
from typing import Dict, List, Optional
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from dotenv import load_dotenv

# Set visualization style
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

# Load environment variables
load_dotenv()

class DORAVisualizer:
    """Class for creating DORA metrics visualizations"""

    def __init__(self, charts_dir: str = "charts"):
        """
        charts_dir: base folder for all generated chart images. Each call to
        start_run() points output_dir at charts_dir/<run_timestamp>/, so every
        run's images land in their own dated folder instead of one flat,
        ever-growing directory.

        Until start_run() is called, output_dir falls back to charts_dir
        itself, so the visualizer still works standalone (tests, one-off
        scripts) without requiring a run timestamp.
        """
        self.charts_dir = charts_dir
        self.run_timestamp: Optional[str] = None
        self.output_dir = charts_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def start_run(self, run_timestamp: str) -> str:
        """Point every subsequent chart-saving call at charts_dir/<run_timestamp>/.
        Call this once at the start of a run, before generating any charts."""
        self.run_timestamp = run_timestamp
        self.output_dir = os.path.join(self.charts_dir, run_timestamp)
        os.makedirs(self.output_dir, exist_ok=True)
        return self.output_dir

    def create_performance_dashboard(self, metrics_data: List[Dict], org_name: str,
                                      historical_data: Optional[List[Dict]] = None):
        """Create a comprehensive dashboard of DORA metrics.

        historical_data: optional list of past run records (same shape produced
        by DORAHistoryStore.load_history), used to render a real trend panel
        instead of the 'not enough data yet' placeholder.
        """
        fig = plt.figure(figsize=(16, 12))

        # Create subplots
        gs = fig.add_gridspec(3, 3)

        # 1. Performance Level Distribution
        ax1 = fig.add_subplot(gs[0, 0])
        self._plot_performance_distribution(ax1, metrics_data)

        # 2. Deployment Frequency
        ax2 = fig.add_subplot(gs[0, 1])
        self._plot_deployment_frequency(ax2, metrics_data)

        # 3. Lead Time Analysis
        ax3 = fig.add_subplot(gs[0, 2])
        self._plot_lead_time(ax3, metrics_data)

        # 4. Change Failure Rate
        ax4 = fig.add_subplot(gs[1, 0])
        self._plot_failure_rate(ax4, metrics_data)

        # 5. Time to Restore
        ax5 = fig.add_subplot(gs[1, 1])
        self._plot_time_to_restore(ax5, metrics_data)

        # 6. Correlation Heatmap
        ax6 = fig.add_subplot(gs[1, 2])
        self._plot_correlation_heatmap(ax6, metrics_data)

        # 7. Trend Analysis (if historical data available) - one panel per metric,
        # each line is a repository so you can see who's improving vs regressing
        ax7a = fig.add_subplot(gs[2, 0])
        ax7b = fig.add_subplot(gs[2, 1])
        ax7c = fig.add_subplot(gs[2, 2])
        self._plot_repo_trends(ax7a, ax7b, ax7c, historical_data)

        # Add title and adjust layout
        plt.suptitle(f'DORA Metrics Dashboard - {org_name}', fontsize=16, fontweight='bold', y=0.98)
        plt.tight_layout(rect=[0, 0.05, 1, 0.96])

        # Save dashboard - no per-file timestamp needed, the parent folder
        # (charts/<run_timestamp>/) already identifies which run this is from
        dashboard_path = os.path.join(self.output_dir, f'dora_dashboard_{org_name}.png')
        plt.savefig(dashboard_path, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"✅ Dashboard saved: {dashboard_path}")
        return dashboard_path

    def _plot_performance_distribution(self, ax, metrics_data):
        """Plot performance level distribution"""
        performance_levels = []
        for repo in metrics_data:
            if 'metrics' in repo:
                performance_levels.append(repo['metrics']['performance_level'])

        if performance_levels:
            from collections import Counter
            counts = Counter(performance_levels)

            # Define colors for each performance level
            colors = {
                'ELITE': '#2ecc71',  # Green
                'HIGH': '#f1c40f',   # Yellow
                'LOW': '#e74c3c',    # Red
                'INSUFFICIENT_DATA': '#95a5a6'  # Gray
            }

            labels = list(counts.keys())
            values = list(counts.values())
            bar_colors = [colors.get(label, '#3498db') for label in labels]

            bars = ax.bar(labels, values, color=bar_colors, edgecolor='black')
            ax.set_title('Performance Level Distribution', fontweight='bold')
            ax.set_ylabel('Number of Repositories')

            # Add value labels on bars
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                       f'{int(height)}', ha='center', va='bottom')
        else:
            ax.text(0.5, 0.5, 'No performance data available',
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Performance Level Distribution', fontweight='bold')

    def _plot_deployment_frequency(self, ax, metrics_data):
        """Plot deployment frequency analysis"""
        freq_data = []
        repo_names = []

        for repo in metrics_data:
            if 'metrics' in repo:
                freq = repo['metrics'].get('deployment_frequency', 'UNKNOWN')
                freq_data.append(freq)
                repo_names.append(repo['repository'])

        if freq_data:
            # Count frequencies
            from collections import Counter
            freq_counts = Counter(freq_data)

            # Create pie chart
            labels = list(freq_counts.keys())
            sizes = list(freq_counts.values())

            # Define colors using numpy for proper color generation
            colors = plt.cm.Set3(np.linspace(0, 1, len(labels)))

            wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=colors,
                                             autopct='%1.1f%%', startangle=90)

            ax.set_title('Deployment Frequency Distribution', fontweight='bold')

            # Equal aspect ratio ensures pie is drawn as circle
            ax.axis('equal')
        else:
            ax.text(0.5, 0.5, 'No deployment frequency data',
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Deployment Frequency Distribution', fontweight='bold')

    def _plot_lead_time(self, ax, metrics_data):
        """Plot lead time for changes"""
        repo_names = []
        lead_times = []

        for repo in metrics_data:
            if 'metrics' in repo:
                repo_names.append(repo['repository'])
                lead_times.append(repo['metrics'].get('lead_time_hours', 0))

        if lead_times:
            # Create bar chart
            x_positions = range(len(repo_names))
            bars = ax.barh(x_positions, lead_times, color='skyblue', edgecolor='black')
            ax.set_title('Lead Time for Changes (hours)', fontweight='bold')
            ax.set_xlabel('Hours')

            # Set y-ticks properly
            ax.set_yticks(x_positions)
            ax.set_yticklabels(repo_names)

            # Add threshold lines
            ax.axvline(x=1, color='green', linestyle='--', alpha=0.5, label='Elite (<1h)')
            ax.axvline(x=24, color='yellow', linestyle='--', alpha=0.5, label='High (<24h)')
            ax.legend()

            # Add value labels
            for bar, time in zip(bars, lead_times):
                width = bar.get_width()
                ax.text(width + max(lead_times)*0.01, bar.get_y() + bar.get_height()/2.,
                       f'{time:.1f}h', ha='left', va='center')
        else:
            ax.text(0.5, 0.5, 'No lead time data',
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Lead Time for Changes', fontweight='bold')

    def _plot_failure_rate(self, ax, metrics_data):
        """Plot change failure rate"""
        repo_names = []
        failure_rates = []

        for repo in metrics_data:
            if 'metrics' in repo:
                repo_names.append(repo['repository'])
                failure_rates.append(repo['metrics'].get('change_failure_rate', 0))

        if failure_rates:
            # Create bar chart with color coding
            colors = []
            for rate in failure_rates:
                if rate <= 15:
                    colors.append('#2ecc71')  # Green
                elif rate <= 30:
                    colors.append('#f1c40f')  # Yellow
                else:
                    colors.append('#e74c3c')  # Red

            x_positions = range(len(repo_names))
            bars = ax.bar(x_positions, failure_rates, color=colors, edgecolor='black')
            ax.set_title('Change Failure Rate (%)', fontweight='bold')
            ax.set_ylabel('Failure Rate %')

            # Set x-ticks properly
            ax.set_xticks(x_positions)
            ax.set_xticklabels(repo_names, rotation=45, ha='right')

            # Add threshold lines
            ax.axhline(y=15, color='green', linestyle='--', alpha=0.5, label='Elite (<15%)')
            ax.axhline(y=30, color='yellow', linestyle='--', alpha=0.5, label='High (<30%)')
            ax.legend()

            # Add value labels
            for bar, rate in zip(bars, failure_rates):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                       f'{rate:.1f}%', ha='center', va='bottom')
        else:
            ax.text(0.5, 0.5, 'No failure rate data',
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Change Failure Rate', fontweight='bold')

    def _plot_time_to_restore(self, ax, metrics_data):
        """Plot time to restore service"""
        repo_names = []
        restore_times = []

        for repo in metrics_data:
            if 'metrics' in repo:
                repo_names.append(repo['repository'])
                restore_times.append(repo['metrics'].get('time_to_restore_hours', 0))

        if restore_times:
            # Create line plot with markers
            x_positions = range(len(repo_names))
            ax.plot(x_positions, restore_times, marker='o', linestyle='-',
                   color='purple', linewidth=2, markersize=8)
            ax.set_title('Time to Restore Service (hours)', fontweight='bold')
            ax.set_ylabel('Hours')

            # Set x-ticks properly
            ax.set_xticks(x_positions)
            ax.set_xticklabels(repo_names, rotation=45, ha='right')
            ax.grid(True, alpha=0.3)

            # Add threshold lines
            ax.axhline(y=1, color='green', linestyle='--', alpha=0.5, label='Elite (<1h)')
            ax.axhline(y=24, color='yellow', linestyle='--', alpha=0.5, label='High (<24h)')
            ax.legend()

            # Add value labels
            for i, (repo, time) in enumerate(zip(repo_names, restore_times)):
                ax.text(i, time + max(restore_times)*0.05, f'{time:.1f}h',
                       ha='center', va='bottom')
        else:
            ax.text(0.5, 0.5, 'No restore time data',
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Time to Restore Service', fontweight='bold')

    def _plot_correlation_heatmap(self, ax, metrics_data):
        """Plot correlation heatmap between metrics"""
        # Prepare data for correlation
        data = []
        for repo in metrics_data:
            if 'metrics' in repo:
                metrics = repo['metrics']
                data.append([
                    metrics.get('lead_time_hours', 0),
                    metrics.get('change_failure_rate', 0),
                    metrics.get('time_to_restore_hours', 0)
                ])

        if len(data) > 2:
            df = pd.DataFrame(data, columns=['Lead Time', 'Failure Rate', 'Restore Time'])
            correlation_matrix = df.corr()

            # Create heatmap
            im = ax.imshow(correlation_matrix, cmap='coolwarm', vmin=-1, vmax=1)

            # Add text annotations
            for i in range(len(correlation_matrix.columns)):
                for j in range(len(correlation_matrix.columns)):
                    text = ax.text(j, i, f'{correlation_matrix.iloc[i, j]:.2f}',
                                 ha="center", va="center", color="white" if abs(correlation_matrix.iloc[i, j]) > 0.5 else "black")

            # Set labels
            ax.set_xticks(range(len(correlation_matrix.columns)))
            ax.set_yticks(range(len(correlation_matrix.columns)))
            ax.set_xticklabels(correlation_matrix.columns, rotation=45, ha='right')
            ax.set_yticklabels(correlation_matrix.columns)
            ax.set_title('Metrics Correlation Heatmap', fontweight='bold')

            # Add colorbar
            plt.colorbar(im, ax=ax)
        else:
            ax.text(0.5, 0.5, 'Insufficient data for correlation',
                   ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Metrics Correlation', fontweight='bold')

    @staticmethod
    def _build_per_repo_history(historical_data: Optional[List[Dict]]) -> Dict[str, List[Dict]]:
        """
        Turn a list of run records into per-repository time series:
            { repo_name: [ {date, lead_time_hours, change_failure_rate,
                             time_to_restore_hours, performance_level}, ... ] }
        Each repo's list is sorted by date. Repos that were missing from a
        given run simply don't get a point for that date - no interpolation.
        """
        per_repo: Dict[str, List[Dict]] = {}
        if not historical_data:
            return per_repo

        for run in historical_data:
            generated_at = run.get('generated_at')
            try:
                run_date = datetime.fromisoformat(generated_at) if generated_at else None
            except ValueError:
                run_date = None
            if run_date is None:
                continue

            for repo in run.get('repositories', []):
                if 'metrics' not in repo:
                    continue
                name = repo.get('repository', 'unknown')
                m = repo['metrics']
                per_repo.setdefault(name, []).append({
                    'date': run_date,
                    'lead_time_hours': m.get('lead_time_hours', 0),
                    'change_failure_rate': m.get('change_failure_rate', 0),
                    'time_to_restore_hours': m.get('time_to_restore_hours', 0),
                    'performance_level': m.get('performance_level', 'UNKNOWN'),
                })

        for name in per_repo:
            per_repo[name].sort(key=lambda r: r['date'])

        return per_repo

    @staticmethod
    def _repo_color_map(repo_names: List[str]) -> Dict[str, tuple]:
        """Stable color per repo, shared across every trend panel so the same
        repo is always the same color whichever chart you're looking at."""
        cmap = plt.cm.get_cmap('tab20', max(len(repo_names), 1))
        return {name: cmap(i % 20) for i, name in enumerate(sorted(repo_names))}

    def _select_repos_for_display(self, per_repo: Dict[str, List[Dict]], max_repos: int) -> List[str]:
        """Cap how many repos get drawn so the legend stays readable.
        Prefers repos with the most historical coverage (most informative line)."""
        ranked = sorted(per_repo.keys(), key=lambda name: len(per_repo[name]), reverse=True)
        return sorted(ranked[:max_repos])

    def _plot_repo_trends(self, ax_lead, ax_failure, ax_restore,
                           historical_data: Optional[List[Dict]], max_repos: int = 10):
        """Three panels (lead time / failure rate / restore time), one line per
        repository per panel, colored consistently across all three."""
        per_repo = self._build_per_repo_history(historical_data)
        not_enough, display_repos, omitted, colors = self._prepare_repo_trend_display(per_repo, max_repos)

        panel_specs = [
            (ax_lead, 'lead_time_hours', 'Lead Time Trend by Repo', 'Hours'),
            (ax_failure, 'change_failure_rate', 'Failure Rate Trend by Repo', '%'),
            (ax_restore, 'time_to_restore_hours', 'Restore Time Trend by Repo', 'Hours'),
        ]

        if not_enough:
            for ax, _, title, _ in panel_specs:
                self._draw_needs_more_runs(ax, title, not_enough)
            return

        for ax, metric_key, title, ylabel in panel_specs:
            self._draw_repo_metric_lines(ax, per_repo, display_repos, colors, metric_key, title, ylabel, omitted)

        # One shared legend (repo names + colors) under the middle panel so it
        # isn't repeated three times
        handles, labels = ax_failure.get_legend_handles_labels()
        ax_failure.legend(handles, labels, loc='upper center', bbox_to_anchor=(0.5, -0.35),
                           ncol=min(len(display_repos), 5), fontsize=6)

    def _plot_single_metric_trend_by_repo(self, ax, historical_data: Optional[List[Dict]],
                                           metric_key: str, title: str, ylabel: str,
                                           max_repos: int = 10, legend: bool = True):
        """Standalone version of one trend panel (used for the per-chart dashboard
        tiles, where each chart is its own image and needs its own legend)."""
        per_repo = self._build_per_repo_history(historical_data)
        not_enough, display_repos, omitted, colors = self._prepare_repo_trend_display(per_repo, max_repos)

        if not_enough:
            self._draw_needs_more_runs(ax, title, not_enough)
            return

        self._draw_repo_metric_lines(ax, per_repo, display_repos, colors, metric_key, title, ylabel, omitted)
        if legend:
            ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.3),
                       ncol=min(len(display_repos), 4), fontsize=7)

    def _prepare_repo_trend_display(self, per_repo: Dict[str, List[Dict]], max_repos: int):
        """Shared setup for both the combined and standalone trend panels:
        checks there's enough history, picks which repos to show, and assigns
        each a stable color. Returns (runs_found_if_not_enough_or_None,
        display_repos, omitted_count, color_map)."""
        MIN_RUNS = 2
        distinct_dates = {pt['date'] for series in per_repo.values() for pt in series}
        if len(distinct_dates) < MIN_RUNS:
            return len(distinct_dates), [], 0, {}

        display_repos = self._select_repos_for_display(per_repo, max_repos)
        omitted = len(per_repo) - len(display_repos)
        colors = self._repo_color_map(display_repos)
        return None, display_repos, omitted, colors

    @staticmethod
    def _draw_needs_more_runs(ax, title, runs_found, min_runs=2):
        ax.text(
            0.5, 0.5, f'Needs \u2265{min_runs} runs.\nFound: {runs_found}',
            ha='center', va='center', transform=ax.transAxes, fontsize=9
        )
        ax.set_title(title, fontweight='bold', fontsize=10)

    @staticmethod
    def _draw_repo_metric_lines(ax, per_repo, display_repos, colors, metric_key, title, ylabel, omitted):
        for repo in display_repos:
            series = per_repo[repo]
            dates = [pt['date'] for pt in series]
            values = [pt[metric_key] for pt in series]
            ax.plot(dates, values, marker='o', markersize=4, linewidth=1.5,
                     label=repo, color=colors[repo])

        subtitle = f' (+{omitted} more not shown)' if omitted > 0 else ''
        ax.set_title(title + subtitle, fontweight='bold', fontsize=10)
        ax.set_xlabel('Date', fontsize=8)
        ax.set_ylabel(ylabel, fontsize=8)
        ax.tick_params(axis='both', labelsize=7, rotation=30)
        ax.grid(True, alpha=0.3)

    # Explanation text shown as a tooltip next to each Overall Performance
    # Dashboard chart in the HTML report.
    DASHBOARD_CHART_EXPLANATIONS = {
        'performance_distribution': "How many repositories fall into each DORA performance tier "
                                     "(LOW / HIGH / ELITE) right now. A repo needs to clear every "
                                     "metric's threshold for its tier, so this is a strict count.",
        'deployment_frequency': "Share of repositories deploying DAILY, WEEKLY, or MONTHLY, based on "
                                 "the GitHub Deployments API. Repos that don't use GitHub Deployments "
                                 "will default to MONTHLY here even if they ship often another way.",
        'lead_time': "Average time from a pull request being opened to it being merged, per repo. "
                     "Dashed lines mark the DORA Elite (<1h) and High (<24h) thresholds for reference.",
        'failure_rate': "Percentage of GitHub Actions workflow runs that ended in failure, per repo. "
                         "Green/yellow/red bars mark Elite (\u226415%), High (\u226430%), and below-High ranges.",
        'time_to_restore': "Average time between a failed workflow run and the next successful run "
                            "for the same repo - a proxy for how fast the team recovers from a failure.",
        'correlation_heatmap': "Pearson correlation between Lead Time, Failure Rate, and Restore Time "
                                "across all repos. Values near 1 mean two metrics tend to move together; "
                                "near 0 means they're largely independent.",
        'trend_lead_time': "Lead time over time, one line per repository, so you can see which repos "
                            "are trending faster or slower across collection runs.",
        'trend_failure_rate': "Change failure rate over time, one line per repository, so you can spot "
                               "repos whose reliability is improving or degrading run over run.",
        'trend_restore_time': "Time to restore service over time, one line per repository, showing "
                               "which teams are getting faster (or slower) at recovering from failures.",
    }

    def create_dashboard_chart_set(self, metrics_data: List[Dict], org_name: str,
                                    historical_data: Optional[List[Dict]] = None,
                                    max_repos: int = 10) -> Dict[str, str]:
        """
        Create each of the Overall Performance Dashboard's charts as its own
        standalone image, mirroring create_repository_chart_set() for individual
        repos. Used so the HTML report can attach a tooltip to each chart
        individually instead of one flat composite image.
        """
        safe_org = org_name.replace('/', '_')
        paths: Dict[str, str] = {}

        def _save(fig, chart_key: str):
            path = os.path.join(self.output_dir, f'dora_dash_{safe_org}_{chart_key}.png')
            fig.savefig(path, dpi=200, bbox_inches='tight')
            plt.close(fig)
            paths[chart_key] = path

        simple_panels = [
            ('performance_distribution', self._plot_performance_distribution),
            ('deployment_frequency', self._plot_deployment_frequency),
            ('lead_time', self._plot_lead_time),
            ('failure_rate', self._plot_failure_rate),
            ('time_to_restore', self._plot_time_to_restore),
            ('correlation_heatmap', self._plot_correlation_heatmap),
        ]
        for chart_key, plot_fn in simple_panels:
            fig, ax = plt.subplots(figsize=(6, 5))
            plot_fn(ax, metrics_data)
            _save(fig, chart_key)

        trend_panels = [
            ('trend_lead_time', 'lead_time_hours', 'Lead Time Trend by Repo', 'Hours'),
            ('trend_failure_rate', 'change_failure_rate', 'Failure Rate Trend by Repo', '%'),
            ('trend_restore_time', 'time_to_restore_hours', 'Restore Time Trend by Repo', 'Hours'),
        ]
        for chart_key, metric_key, title, ylabel in trend_panels:
            fig, ax = plt.subplots(figsize=(6, 5))
            self._plot_single_metric_trend_by_repo(ax, historical_data, metric_key, title, ylabel,
                                                     max_repos=max_repos, legend=True)
            _save(fig, chart_key)

        return paths

    def create_individual_repository_report(self, repo_data: Dict):
        """Create detailed visualization for a single repository"""
        if 'metrics' not in repo_data:
            return None

        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        axes = axes.flatten()

        repo_name = repo_data['repository']
        metrics = repo_data['metrics']

        # 1. Performance Gauge Chart
        self._create_gauge_chart(axes[0], metrics['performance_level'])

        # 2. Metrics Radar Chart
        self._create_radar_chart(axes[1], metrics, repo_name)

        # 3. Metrics Comparison with DORA Standards
        self._create_comparison_chart(axes[2], metrics)

        # 4. Data Sources and Confidence
        if 'data_sources' in repo_data:
            self._create_data_sources_chart(axes[3], repo_data['data_sources'])

        plt.suptitle(f'DORA Metrics Report - {repo_name}', fontsize=14, fontweight='bold', y=0.98)
        plt.tight_layout(rect=[0, 0, 1, 0.96])

        # Save report - the parent folder (charts/<run_timestamp>/) already
        # identifies which run this came from, so the filename just needs to
        # be unique within that run (repo name is enough for that).
        report_path = os.path.join(self.output_dir, f'dora_report_{repo_name}.png')
        plt.savefig(report_path, dpi=300, bbox_inches='tight')
        plt.close()

        return report_path

    # Explanation text shown as a tooltip next to each individual-repo chart in
    # the HTML report. Kept alongside the chart-generation code so the two
    # never drift apart when a chart's content changes.
    CHART_EXPLANATIONS = {
        'gauge': "Shows this repo's overall DORA performance level (LOW / HIGH / ELITE). "
                 "This is an all-or-nothing gate: every one of the four DORA metrics has to "
                 "clear a tier's threshold simultaneously for the repo to be rated at that tier.",
        'radar': "Normalizes all four DORA metrics onto a 0-1 scale (1 = best) so you can see "
                 "at a glance whether performance is balanced across metrics or lopsided - e.g. "
                 "fast deployments but slow recovery from failures.",
        'comparison': "Compares this repo's actual Lead Time, Failure Rate, and Restore Time "
                      "against the official DORA Elite and High benchmarks, so you can see exactly "
                      "how far off - or ahead of - each standard the repo is.",
        'data_sources': "Shows which GitHub API feeds each metric (deployments / workflow runs / "
                         "pull requests) and how much data backs it. Solid color = confident "
                         "(5+ data points), faded = thin data, red-bordered 'no data' = a default "
                         "value is being used because nothing was found.",
    }

    def create_repository_chart_set(self, repo_data: Dict) -> Optional[Dict[str, str]]:
        """
        Create the same 4 charts as create_individual_repository_report(), but as
        separate standalone image files instead of one composite figure.

        This exists so the HTML report can lay each chart out in its own tile
        with its own tooltip - a single flattened PNG can't carry per-chart
        hover text, four separate images can.

        Returns {'gauge': path, 'radar': path, 'comparison': path,
                 'data_sources': path} - 'data_sources' is omitted if the repo
        has no data_sources info.
        """
        if 'metrics' not in repo_data:
            return None

        repo_name = repo_data['repository']
        metrics = repo_data['metrics']
        safe_name = repo_name.replace('/', '_')
        paths: Dict[str, str] = {}

        def _save(fig, chart_key: str):
            path = os.path.join(self.output_dir, f'dora_chart_{safe_name}_{chart_key}.png')
            fig.savefig(path, dpi=200, bbox_inches='tight')
            plt.close(fig)
            paths[chart_key] = path

        fig, ax = plt.subplots(figsize=(6, 5))
        self._create_gauge_chart(ax, metrics['performance_level'])
        _save(fig, 'gauge')

        fig, ax = plt.subplots(figsize=(6, 5))
        self._create_radar_chart(ax, metrics, repo_name)
        _save(fig, 'radar')

        fig, ax = plt.subplots(figsize=(6, 5))
        self._create_comparison_chart(ax, metrics)
        _save(fig, 'comparison')

        if 'data_sources' in repo_data:
            fig, ax = plt.subplots(figsize=(6, 5))
            self._create_data_sources_chart(ax, repo_data['data_sources'])
            _save(fig, 'data_sources')

        return paths

    def _create_gauge_chart(self, ax, performance_level):
        """Create gauge chart for performance level"""
        # Define levels and colors
        levels = ['LOW', 'HIGH', 'ELITE']
        colors = ['#e74c3c', '#f1c40f', '#2ecc71']

        # Create gauge
        level_index = levels.index(performance_level) if performance_level in levels else 0
        ax.barh([0], [1], color='lightgray', height=0.3)
        ax.barh([0], [(level_index + 1) / len(levels)],
               color=colors[level_index], height=0.3)

        ax.set_xlim(0, 1)
        ax.set_ylim(-0.5, 0.5)
        ax.set_yticks([])
        ax.set_xticks([])
        ax.set_title(f'Performance Level: {performance_level}', fontweight='bold')

        # Add level markers
        for i, (level, color) in enumerate(zip(levels, colors)):
            x_pos = (i + 0.5) / len(levels)
            ax.text(x_pos, -0.2, level, ha='center', va='top',
                   fontweight='bold' if level == performance_level else 'normal',
                   color=color)

    def _create_radar_chart(self, ax, metrics, repo_name):
        """Create radar chart for DORA metrics"""
        # Categories and values
        categories = ['Deployment\nFrequency', 'Lead Time', 'Failure Rate', 'Time to Restore']

        # Normalize values (lower is better for most metrics)
        # This is simplified - in reality you'd need proper normalization
        values = [
            self._normalize_deployment_freq(metrics.get('deployment_frequency', 'UNKNOWN')),
            self._normalize_lead_time(metrics.get('lead_time_hours', 168)),
            self._normalize_failure_rate(metrics.get('change_failure_rate', 50)),
            self._normalize_restore_time(metrics.get('time_to_restore_hours', 24))
        ]

        # Complete the circle
        values += values[:1]
        angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
        angles += angles[:1]

        # Create radar chart
        ax.plot(angles, values, 'o-', linewidth=2)
        ax.fill(angles, values, alpha=0.25)
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories)
        ax.set_ylim(0, 1)
        ax.set_title('Metrics Radar Chart', fontweight='bold')
        ax.grid(True)

    def _normalize_deployment_freq(self, freq):
        """Normalize deployment frequency"""
        mapping = {
            'DAILY': 1.0,
            'WEEKLY': 0.75,
            'MONTHLY': 0.5,
            'YEARLY': 0.25,
            'UNKNOWN': 0
        }
        return mapping.get(freq, 0)

    def _normalize_lead_time(self, hours):
        """Normalize lead time (lower is better)"""
        return max(0, 1 - min(hours / 168, 1))  # 1 week max

    def _normalize_failure_rate(self, rate):
        """Normalize failure rate (lower is better)"""
        return max(0, 1 - min(rate / 100, 1))

    def _normalize_restore_time(self, hours):
        """Normalize restore time (lower is better)"""
        return max(0, 1 - min(hours / 168, 1))  # 1 week max

    def _create_comparison_chart(self, ax, metrics):
        """Create comparison chart with DORA standards"""
        categories = ['Lead Time', 'Failure Rate', 'Restore Time']
        actual = [
            metrics.get('lead_time_hours', 0),
            metrics.get('change_failure_rate', 0),
            metrics.get('time_to_restore_hours', 0)
        ]

        # DORA Elite standards
        elite = [1, 15, 1]

        # DORA High standards
        high = [24, 30, 24]

        x = range(len(categories))
        width = 0.25

        ax.bar([i - width for i in x], actual, width, label='Actual', color='#3498db')
        ax.bar(x, elite, width, label='Elite Standard', color='#2ecc71')
        ax.bar([i + width for i in x], high, width, label='High Standard', color='#f1c40f')

        ax.set_xticks(x)
        ax.set_xticklabels(categories, rotation=45, ha='right')
        ax.set_ylabel('Hours / Percentage')
        ax.set_title('Comparison with DORA Standards', fontweight='bold')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')

    # Fixed, canonical order + colors so every repo's chart lines up the same
    # way and is comparable at a glance across the whole HTML report.
    _SOURCE_ORDER = ['deployments', 'workflow_runs', 'pull_requests']
    _SOURCE_COLORS = {
        'deployments': '#3498db',     # blue
        'workflow_runs': '#9b59b6',   # purple
        'pull_requests': '#2ecc71',   # green
        'unknown': '#7f8c8d',         # gray, fallback for anything unexpected
    }

    def _create_data_sources_chart(self, ax, data_sources):
        """Chart showing which source feeds each metric, and how much data backed
        it. Each source gets its own fixed color (not a shared heatmap gradient)
        so 'which source' reads instantly; cell opacity encodes confidence
        (full color = validated data, faded = missing/low data), and the count
        of underlying data points is annotated in the cell.
        """
        metrics = list(data_sources.keys())

        # Always show every known source column, even if unused by this repo,
        # so columns land in the same position on every repo's chart.
        sources_present = {data_sources[m].get('method', 'unknown') for m in metrics}
        columns = list(self._SOURCE_ORDER)
        for s in sorted(sources_present - set(columns)):
            columns.append(s)  # any unexpected source name still gets shown

        ax.set_xlim(0, len(columns))
        ax.set_ylim(0, len(metrics))

        for i, metric in enumerate(metrics):
            row_y = len(metrics) - 1 - i  # top-to-bottom row order
            info = data_sources[metric]
            source = info.get('method', 'unknown')
            count = info.get('count', 0)
            valid = info.get('valid', False)
            col_x = columns.index(source)

            color = self._SOURCE_COLORS.get(source, self._SOURCE_COLORS['unknown'])
            # High confidence = validated data with a healthy sample size;
            # low confidence = technically "valid" but thin, or no data at all.
            if valid and count >= 5:
                alpha, edge = 0.9, 'none'
            elif valid and count > 0:
                alpha, edge = 0.5, '#7f8c8d'
            else:
                alpha, edge = 0.15, '#c0392b'

            ax.add_patch(plt.Rectangle(
                (col_x, row_y), 1, 1, facecolor=color, alpha=alpha,
                edgecolor=edge, linewidth=1.5
            ))

            label = f'{count} pts' if valid else 'no data'
            ax.text(col_x + 0.5, row_y + 0.5, label, ha='center', va='center',
                     fontsize=8, fontweight='bold',
                     color='black' if alpha >= 0.5 else '#555555')

        ax.set_xticks([c + 0.5 for c in range(len(columns))])
        ax.set_xticklabels(columns, rotation=45, ha='right')
        ax.set_yticks([len(metrics) - 1 - i + 0.5 for i in range(len(metrics))])
        ax.set_yticklabels([m.replace('_', ' ').title() for m in metrics])
        ax.set_title('Data Sources & Confidence', fontweight='bold')
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(False)

        # Confidence legend (color = source is separate and visible from column
        # headers already; this legend explains the opacity/border encoding)
        legend_elements = [
            plt.matplotlib.patches.Patch(facecolor='gray', alpha=0.9, edgecolor='none', label='High confidence (\u22655 data points)'),
            plt.matplotlib.patches.Patch(facecolor='gray', alpha=0.5, edgecolor='#7f8c8d', label='Low confidence (<5 data points)'),
            plt.matplotlib.patches.Patch(facecolor='gray', alpha=0.15, edgecolor='#c0392b', label='No data (using default)'),
        ]
        ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, -0.3),
                   fontsize=6, ncol=1, frameon=False)

    def create_historical_trend_chart(self, historical_data: List[Dict], max_repos: int = 15):
        """Create trend charts from historical DORA data, broken down by repository.

        Layout:
          top-left:     performance level heatmap (repo x collection date)
          top-right:    lead time trend, one line per repo
          bottom-left:  failure rate trend, one line per repo
          bottom-right: restore time trend, one line per repo
        """
        per_repo = self._build_per_repo_history(historical_data)
        if not per_repo:
            return None

        distinct_dates = {pt['date'] for series in per_repo.values() for pt in series}
        if len(distinct_dates) < 2:
            return None

        display_repos = self._select_repos_for_display(per_repo, max_repos)
        omitted = len(per_repo) - len(display_repos)
        colors = self._repo_color_map(display_repos)

        fig, axes = plt.subplots(2, 2, figsize=(16, 11))
        axes = axes.flatten()

        # 1. Performance Level heatmap (repo x date) - shows every repo's level
        # at every collection point, which a stacked area chart can't do.
        self._plot_performance_heatmap(axes[0], per_repo, display_repos)

        # 2-4. Per-repo metric trends
        panel_specs = [
            (axes[1], 'lead_time_hours', 'Lead Time Trend by Repo', 'Hours'),
            (axes[2], 'change_failure_rate', 'Failure Rate Trend by Repo', 'Failure Rate (%)'),
            (axes[3], 'time_to_restore_hours', 'Restore Time Trend by Repo', 'Hours'),
        ]
        for ax, metric_key, title, ylabel in panel_specs:
            for repo in display_repos:
                series = per_repo[repo]
                dates = [pt['date'] for pt in series]
                values = [pt[metric_key] for pt in series]
                ax.plot(dates, values, marker='o', markersize=5, linewidth=2,
                         label=repo, color=colors[repo])
            subtitle = f' (+{omitted} more not shown)' if omitted > 0 else ''
            ax.set_title(title + subtitle, fontweight='bold')
            ax.set_xlabel('Date')
            ax.set_ylabel(ylabel)
            ax.grid(True, alpha=0.3)
            ax.tick_params(axis='x', rotation=30)

        # One shared legend for all repo lines, placed below the whole figure
        handles, labels = axes[1].get_legend_handles_labels()
        fig.legend(handles, labels, loc='lower center', ncol=min(len(display_repos), 8),
                   fontsize=8, bbox_to_anchor=(0.5, -0.02))

        plt.suptitle('DORA Metrics Historical Trends by Repository', fontsize=16, fontweight='bold', y=0.98)
        plt.tight_layout(rect=[0, 0.05, 1, 0.96])

        # Save trend chart
        trend_path = os.path.join(self.output_dir, 'dora_trends.png')
        plt.savefig(trend_path, dpi=300, bbox_inches='tight')
        plt.close()

        return trend_path

    def _plot_performance_heatmap(self, ax, per_repo: Dict[str, List[Dict]], display_repos: List[str]):
        """Grid of repo (row) x collection date (column), colored by performance
        level at that point in time. Lets you spot which repos are trending
        towards ELITE and which are sliding towards LOW at a glance."""
        level_to_value = {'LOW': 1, 'HIGH': 2, 'ELITE': 3, 'UNKNOWN': 0}
        level_colors = ['#ecf0f1', '#e74c3c', '#f1c40f', '#2ecc71']  # unknown, low, high, elite
        cmap = plt.matplotlib.colors.ListedColormap(level_colors)

        all_dates = sorted({pt['date'] for repo in display_repos for pt in per_repo[repo]})
        date_labels = [d.strftime('%m-%d') for d in all_dates]

        matrix = np.zeros((len(display_repos), len(all_dates)))
        for i, repo in enumerate(display_repos):
            by_date = {pt['date']: pt['performance_level'] for pt in per_repo[repo]}
            for j, d in enumerate(all_dates):
                matrix[i, j] = level_to_value.get(by_date.get(d, 'UNKNOWN'), 0)

        im = ax.imshow(matrix, cmap=cmap, aspect='auto', vmin=0, vmax=3)
        ax.set_xticks(range(len(date_labels)))
        ax.set_xticklabels(date_labels, rotation=45, ha='right', fontsize=8)
        ax.set_yticks(range(len(display_repos)))
        ax.set_yticklabels(display_repos, fontsize=8)
        ax.set_title('Performance Level by Repository Over Time', fontweight='bold')

        cbar = plt.colorbar(im, ax=ax, ticks=[0.4, 1.1, 1.9, 2.6])
        cbar.ax.set_yticklabels(['No data', 'LOW', 'HIGH', 'ELITE'], fontsize=8)