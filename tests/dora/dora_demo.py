# main_with_viz_fixed.py
import json
import os
from datetime import datetime, timedelta
import shutil
from typing import List, Dict, Optional
import pandas as pd
import base64
from dotenv import load_dotenv
import random

# Import the fixed visualizer
from dora_visualization import DORAVisualizer
from github_client import GitHubClient
from dora_metrics_calculator import DORAMetricsCalculator
from dora_history import DORAHistoryStore
from dashboard_generation import DashboardHTMLGenerator


class DORAFramework:
    """DORA Framework with fixed Unicode handling for Windows"""

    def __init__(self, organization: str = "easyjet-dev"):
        # Chart images and report deliverables (html/text/csv/xlsx/json) live in
        # separate top-level folders, each organized into a per-run,
        # timestamped subfolder: charts/<run_timestamp>/, reports/<run_timestamp>/.
        # That keeps every run's output self-contained and browsable by date,
        # instead of one flat folder that only ever holds the latest run.
        self.charts_base_dir = "charts"
        self.reports_base_dir = "reports"
        self.reports_dir = self.reports_base_dir  # overwritten per run in run_analysis()

        self.visualizer = DORAVisualizer(charts_dir=self.charts_base_dir)
        self.organization = organization
        self.github_client = GitHubClient(organization=organization)
        self.metrics_calculator = DORAMetricsCalculator()
        self.html_generator = DashboardHTMLGenerator(self.visualizer)
        # Lives outside both charts/ and reports/ on purpose - it needs to
        # survive indefinitely across runs to power trend analysis, regardless
        # of what happens to any individual run's charts or reports.
        self.history_store = DORAHistoryStore()

    def cleanup_old_reports(self):
        """Delete every past run's charts and reports.

        NOT called automatically - each run now lives in its own dated
        subfolder under charts/ and reports/, so old runs are meant to be kept
        around for browsing/comparison. Call this yourself if you want to
        reclaim disk space; it does not touch dora_history/ (trend data).
        """
        for base_dir in (self.charts_base_dir, self.reports_base_dir):
            if not os.path.exists(base_dir):
                print(f"  '{base_dir}' doesn't exist yet.")
                continue

            print(f"\nCleaning up old runs in '{base_dir}'...")
            for filename in os.listdir(base_dir):
                file_path = os.path.join(base_dir, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                        print(f"  Deleted: {file_path}")
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                        print(f"  Deleted folder: {file_path}")
                except Exception as e:
                    print(f"  Error deleting {file_path}: {e}")
            print(f"  Cleanup complete for '{base_dir}'!")

    def run_analysis(self):
        """Run complete DORA analysis"""
        print("="*60)
        print("DORA Framework Analysis")
        print("="*60)

        # One timestamp shared by every artifact this run produces, so charts
        # and reports from the same run land in matching dated subfolders
        # (charts/<run_timestamp>/, reports/<run_timestamp>/) instead of each
        # file picking its own timestamp independently.
        run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.visualizer.start_run(run_timestamp)
        self.reports_dir = os.path.join(self.reports_base_dir, run_timestamp)
        os.makedirs(self.reports_dir, exist_ok=True)
        print(f"Run timestamp: {run_timestamp}")
        print(f"Charts folder: {self.visualizer.output_dir}")
        print(f"Reports folder: {self.reports_dir}")

        # Create metrics data (now from real GitHub data)
        if self.github_client.is_authenticated():
            print(f"Using GitHub token for organization: {self.organization}")
            print(f"Testing GitHub connection...")

            if self.github_client.test_connection():
                print("✅ GitHub connection successful")
                metrics_data = self._get_real_github_metrics()
            else:
                print("❌ GitHub connection failed. Using sample data.")
                metrics_data = self._create_sample_metrics()
        else:
            print("No GitHub token found. Using sample data.")
            print("Set GITHUB_TOKEN in .env file to fetch real data.")
            metrics_data = self._create_sample_metrics()

        # Persist this run to history BEFORE anything else touches metrics_data,
        # so a later error in report generation can't cost us this data point.
        history_path = self.history_store.save_run(metrics_data, self.organization)
        if history_path:
            print(f"  Saved run to history: {history_path}")

        # Load full history (including the run we just saved) to power trend charts
        historical_runs = self.history_store.load_history(self.organization)
        print(f"  {len(historical_runs)} historical run(s) available for trend analysis")

        # Create visualizations
        print(
            f"\nCreating visualizations for {len(metrics_data)} repositories...")

        # 1. Create main dashboard (trend panel renders real data once >=2 runs exist)
        dashboard_path = self.visualizer.create_performance_dashboard(
            metrics_data, self.organization, historical_data=historical_runs
        )
        print(f"  Created dashboard: {os.path.basename(dashboard_path)}")

        # 1a. Split version of the same dashboard - one image per chart, used by
        # the HTML report so each chart can carry its own tooltip
        dashboard_chart_set = self.visualizer.create_dashboard_chart_set(
            metrics_data, self.organization, historical_data=historical_runs
        )

        # 1b. Dedicated historical trend chart (separate PNG with 4 panels),
        # only worth generating once there's more than one data point.
        trend_chart_path = None
        if len(historical_runs) >= 2:
            trend_chart_path = self.visualizer.create_historical_trend_chart(historical_runs)
            if trend_chart_path:
                print(f"  Created trend chart: {os.path.basename(trend_chart_path)}")

        # 2. Create individual reports (one composite PNG per repo, used for the
        # "download full report" link) plus a split chart set per repo (four
        # separate images, used by the interactive dropdown view so each chart
        # can carry its own tooltip)
        repo_chart_sets: Dict[str, Dict[str, str]] = {}
        repo_composite_paths: Dict[str, str] = {}
        for repo_data in metrics_data:
            report_path = self.visualizer.create_individual_repository_report(
                repo_data)
            if report_path:
                repo_composite_paths[repo_data['repository']] = report_path
                print(
                    f"  Created report for {repo_data['repository']}: {os.path.basename(report_path)}")

            chart_set = self.visualizer.create_repository_chart_set(repo_data)
            if chart_set:
                repo_chart_sets[repo_data['repository']] = chart_set

        # 3. Create metrics table
        self._create_metrics_table(metrics_data)

        # 4. Generate HTML report (without emojis for Windows compatibility).
        # HTML assembly lives in dashboard_generation.py, not here, so the
        # (large) template is easy to find and edit on its own.
        html_path = self.html_generator.generate(
            metrics_data=metrics_data,
            organization=self.organization,
            dashboard_path=dashboard_path,
            repo_chart_sets=repo_chart_sets,
            dashboard_chart_set=dashboard_chart_set,
            repo_composite_paths=repo_composite_paths,
            reports_dir=self.reports_dir,
            run_timestamp=run_timestamp,
            historical_data=historical_runs,
        )
        print(f"  Created HTML report: {os.path.basename(html_path)}")

        # 5. Generate text report
        text_path = self.generate_text_report(metrics_data, historical_runs)
        print(f"  Created text report: {os.path.basename(text_path)}")

        # 6. Save raw metrics data as JSON
        json_path = os.path.join(self.reports_dir, f'dora_metrics_raw_{run_timestamp}.json')
        with open(json_path, 'w') as f:
            json.dump({
                'organization': self.organization,
                'generated_at': datetime.now().isoformat(),
                'repository_count': len(metrics_data),
                'metrics_data': metrics_data
            }, f, indent=2)
        print(f"  Created raw data: {os.path.basename(json_path)}")

        print(f"\n✅ Charts saved to '{self.visualizer.output_dir}'")
        print(f"✅ Reports saved to '{self.reports_dir}'")

    def _get_real_github_metrics(self) -> List[Dict]:
        """Fetch real metrics from GitHub API"""
        print("\n📊 Fetching real GitHub data...")

        # Fetch repositories
        repos = self.github_client.fetch_repositories(
            limit=20, exclude_forks=False)
        if not repos:
            print("No repositories found or error fetching repositories.")
            return self._create_sample_metrics()

        print(f"Found {len(repos)} repositories. Analyzing...")

        metrics_data = []
        analyzed_count = 0

        for repo in repos:
            # Get raw data from GitHub
            raw_data = self.github_client.get_repository_metrics(repo)

            if raw_data:
                # Calculate DORA metrics using the calculator
                repo_metrics = self.metrics_calculator.calculate_dora_metrics_from_raw(
                    raw_data)
                if repo_metrics:
                    metrics_data.append(repo_metrics)
                    analyzed_count += 1
                    print(f"  ✅ Analyzed {repo}")

        print(f"✅ Successfully analyzed {analyzed_count} repositories.")
        return metrics_data

    def _create_sample_metrics(self) -> List[Dict]:
        """Create realistic sample metrics data (fallback when no GitHub token)"""
        # Sample repository names based on common patterns
        sample_repos = [
            'api-gateway',
            'user-service',
            'payment-service',
            'notification-service',
            'frontend-app',
            'mobile-app',
            'admin-dashboard',
            'data-pipeline',
            'analytics-service',
            'auth-service',
            'search-service',
            'inventory-service'
        ]

        # Shuffle and take 6-8 repos
        random.shuffle(sample_repos)
        selected_repos = sample_repos[:random.randint(6, 8)]

        metrics_data = []

        for repo in selected_repos:
            # Create realistic variations based on repo type
            if 'api' in repo or 'service' in repo:
                # Services typically have better metrics
                deployment_freq = random.choice(['DAILY', 'WEEKLY', 'WEEKLY'])
                lead_time = random.uniform(2, 12)
                failure_rate = random.uniform(5, 20)
                restore_time = random.uniform(1, 6)
            elif 'frontend' in repo or 'app' in repo or 'dashboard' in repo:
                # Frontend apps vary more
                deployment_freq = random.choice(
                    ['WEEKLY', 'MONTHLY', 'WEEKLY'])
                lead_time = random.uniform(8, 36)
                failure_rate = random.uniform(8, 25)
                restore_time = random.uniform(4, 16)
            else:
                # Other repos
                deployment_freq = random.choice(['WEEKLY', 'MONTHLY'])
                lead_time = random.uniform(6, 24)
                failure_rate = random.uniform(10, 30)
                restore_time = random.uniform(3, 12)

            metrics = {
                'deployment_frequency': deployment_freq,
                'lead_time_hours': round(lead_time, 1),
                'change_failure_rate': round(failure_rate, 1),
                'time_to_restore_hours': round(restore_time, 1)
            }

            # Calculate performance level using the calculator
            metrics['performance_level'] = self.metrics_calculator._calculate_performance_level(
                metrics)

            # Generate realistic data source counts
            deployments_count = random.randint(
                5, 50) if deployment_freq == 'DAILY' else random.randint(2, 20)
            workflow_runs_count = random.randint(20, 200)
            prs_count = random.randint(5, 40)

            metrics_data.append({
                'repository': repo,
                'metrics': metrics,
                'data_sources': self.metrics_calculator._get_data_sources(
                    [{}] * deployments_count,  # Simulate deployments
                    [{}] * workflow_runs_count,  # Simulate workflow runs
                    [{}] * prs_count  # Simulate PRs
                ),
                'last_updated': datetime.now().isoformat(),
                'data_points': {
                    'deployments_analyzed': deployments_count,
                    'workflow_runs_analyzed': workflow_runs_count,
                    'pull_requests_analyzed': prs_count,
                    'analysis_period_days': 30
                }
            })

        return metrics_data

    def _create_metrics_table(self, metrics_data: List[Dict]):
        """Create a CSV summary table"""
        summary_data = []

        for repo in metrics_data:
            if 'metrics' in repo:
                summary_data.append({
                    'Repository': repo['repository'],
                    'Performance Level': repo['metrics']['performance_level'],
                    'Deployment Frequency': repo['metrics']['deployment_frequency'],
                    'Lead Time (hours)': repo['metrics']['lead_time_hours'],
                    'Change Failure Rate (%)': repo['metrics']['change_failure_rate'],
                    'Time to Restore (hours)': repo['metrics']['time_to_restore_hours'],
                    'Deployments Analyzed': repo.get('data_points', {}).get('deployments_analyzed', 0),
                    'Workflow Runs Analyzed': repo.get('data_points', {}).get('workflow_runs_analyzed', 0),
                    'PRs Analyzed': repo.get('data_points', {}).get('pull_requests_analyzed', 0),
                    'Last Updated': repo.get('last_updated', ''),
                    'Collection Date': datetime.now().strftime('%Y-%m-%d')
                })

        if summary_data:
            df = pd.DataFrame(summary_data)

            # Save as CSV
            csv_path = os.path.join(self.reports_dir, 'dora_metrics_summary.csv')
            df.to_csv(csv_path, index=False)
            print(f"  Created metrics table: {os.path.basename(csv_path)}")

            # Save as Excel
            try:
                excel_path = os.path.join(self.reports_dir, 'dora_metrics_summary.xlsx')
                df.to_excel(excel_path, index=False, engine='openpyxl')
                print(
                    f"  Created Excel report: {os.path.basename(excel_path)}")
            except ImportError:
                print("  Note: Install openpyxl for Excel export: pip install openpyxl")
            except Exception as e:
                print(f"  Error creating Excel file: {e}")

    def generate_text_report(self, metrics_data: List[Dict], historical_runs: Optional[List[Dict]] = None):
        """Generate a simple text report for Windows compatibility"""
        historical_runs = historical_runs or []
        text_content = f"""DORA METRICS REPORT
========================
Organization: {self.organization}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Repositories Analyzed: {len(metrics_data)}

METRICS SUMMARY:
----------------
"""

        for repo in metrics_data:
            if 'metrics' in repo:
                metrics = repo['metrics']
                data_points = repo.get('data_points', {})
                text_content += f"""
Repository: {repo['repository']}
Performance Level: {metrics['performance_level']}
Deployment Frequency: {metrics['deployment_frequency']}
Lead Time: {metrics['lead_time_hours']:.1f} hours
Change Failure Rate: {metrics['change_failure_rate']:.1f}%
Time to Restore: {metrics['time_to_restore_hours']:.1f} hours
Data Points: {data_points.get('deployments_analyzed', 0)} deployments, {data_points.get('workflow_runs_analyzed', 0)} workflow runs, {data_points.get('pull_requests_analyzed', 0)} PRs
----------------
"""

        # Calculate averages
        avg_lead_time = sum(r['metrics']['lead_time_hours']
                            for r in metrics_data if 'metrics' in r) / len(metrics_data)
        avg_failure_rate = sum(r['metrics']['change_failure_rate']
                               for r in metrics_data if 'metrics' in r) / len(metrics_data)
        elite_count = len(
            [r for r in metrics_data if r['metrics']['performance_level'] == 'ELITE'])

        text_content += f"""
OVERALL STATISTICS:
-------------------
Average Lead Time: {avg_lead_time:.1f} hours
Average Failure Rate: {avg_failure_rate:.1f}%
Elite Repositories: {elite_count}/{len(metrics_data)} ({elite_count/len(metrics_data)*100:.0f}%)

RECOMMENDATIONS:
---------------
1. Focus on reducing lead time for changes
2. Monitor change failure rate regularly
3. Implement automated recovery processes
4. Increase deployment frequency
5. Conduct regular retrospectives
6. Share best practices across teams
7. Set up DORA metrics monitoring

DORA Performance Levels:
- ELITE: Daily deployments, <1h lead time, <15% failure rate, <1h restore
- HIGH: Weekly deployments, <24h lead time, <30% failure rate, <24h restore
- LOW: Monthly or less frequent deployments

DATA SOURCES:
------------
- GitHub Deployments API
- GitHub Actions Workflow Runs
- GitHub Pull Requests API
- Analysis period: Last 30 days

TREND ANALYSIS:
---------------
Historical runs available: {len(historical_runs)}
{"Trend chart generated - see dora_trends_*.png in this folder." if len(historical_runs) >= 2 else
 "Not enough history yet to plot a trend (need at least 2 runs). Run this analysis "
 "again on a later date to start building the trend chart."}
"""

        text_path = os.path.join(self.reports_dir, f'dora_report_{self.organization}.txt')

        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(text_content)

        print(f"  Created text report: {os.path.basename(text_path)}")
        return text_path


def main():
    """Main execution function"""
    load_dotenv()

    org = os.getenv('GITHUB_ORG', 'easyjet-dev')

    print("DORA Metrics Dashboard Generator")
    print("="*50)

    # Check for GitHub token
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        print("⚠️  WARNING: GITHUB_TOKEN not found in .env file")
        print("   The analysis will use sample data.")
        print("   To fetch real GitHub data, add your token to .env:")
        print("   GITHUB_TOKEN=your_github_token_here")
        print()

    try:
        # Initialize and run framework
        dora = DORAFramework(org)
        dora.run_analysis()

    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("   Install required packages: pip install matplotlib seaborn pandas numpy requests python-dotenv")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()