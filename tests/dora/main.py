
# main_with_viz_fixed.py
import json
import os
from datetime import datetime, timedelta
import shutil
from typing import List, Dict, Optional
import pandas as pd
import base64
import requests
from dotenv import load_dotenv
import time

# Import the fixed visualizer
from dora_visualization import DORAVisualizer


class DORAFrameworkFixed:
    """DORA Framework with fixed Unicode handling for Windows"""

    def __init__(self, organization: str = "easyjet-dev"):
        self.visualizer = DORAVisualizer()
        self.organization = organization
        self.github_token = os.getenv('GITHUB_TOKENS', '')
        self.headers = {
            'Authorization': f'token {self.github_token}',
            'Accept': 'application/vnd.github.v3+json',
            "X-GitHub-Api-Version": "2022-11-28"
        } if self.github_token else {}
        self.base_url = 'https://api.github.com'

    def cleanup_old_reports(self):
        """Delete all existing report files"""
        reports_dir = self.visualizer.output_dir

        if os.path.exists(reports_dir):
            print(f"\nCleaning up old reports in '{reports_dir}'...")

            # Delete all files
            for filename in os.listdir(reports_dir):
                file_path = os.path.join(reports_dir, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                        print(f"  Deleted: {filename}")
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                        print(f"  Deleted folder: {filename}")
                except Exception as e:
                    print(f"  Error deleting {file_path}: {e}")

            print("  Cleanup complete!")
        else:
            print(f"  Reports directory '{reports_dir}' doesn't exist yet.")

    def run_analysis(self):
        """Run complete DORA analysis"""
        print("="*60)
        print("DORA Framework Analysis")
        print("="*60)

        # Clean up old reports first
        self.cleanup_old_reports()

        # Create metrics data (now from real GitHub data)
        if self.github_token:
            print(f"Using GitHub token for organization: {self.organization}")
            metrics_data = self._get_real_github_metrics()
        else:
            print("No GitHub token found. Using sample data.")
            print("Set GITHUB_TOKEN in .env file to fetch real data.")
            metrics_data = self._create_sample_metrics()

        # Create visualizations
        print(
            f"\nCreating visualizations for {len(metrics_data)} repositories...")

        # 1. Create main dashboard
        dashboard_path = self.visualizer.create_performance_dashboard(
            metrics_data, self.organization
        )
        print(f"  Created dashboard: {os.path.basename(dashboard_path)}")

        # 2. Create individual reports
        for repo_data in metrics_data:
            report_path = self.visualizer.create_individual_repository_report(
                repo_data)
            if report_path:
                print(
                    f"  Created report for {repo_data['repository']}: {os.path.basename(report_path)}")

        # 3. Create metrics table
        self._create_metrics_table(metrics_data)

        # 4. Generate HTML report (without emojis for Windows compatibility)
        html_path = self._generate_windows_compatible_html(
            metrics_data, dashboard_path)
        print(f"  Created HTML report: {os.path.basename(html_path)}")

        # 5. Generate text report
        text_path = self.generate_text_report(metrics_data)
        print(f"  Created text report: {os.path.basename(text_path)}")

        # 6. Save raw metrics data as JSON
        json_path = os.path.join(self.visualizer.output_dir,
                                 f'dora_metrics_raw_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        with open(json_path, 'w') as f:
            json.dump({
                'organization': self.organization,
                'generated_at': datetime.now().isoformat(),
                'repository_count': len(metrics_data),
                'metrics_data': metrics_data
            }, f, indent=2)
        print(f"  Created raw data: {os.path.basename(json_path)}")

        print(f"\n✅ All outputs created in 'reports' directory!")

    def _get_real_github_metrics(self) -> List[Dict]:
        """Fetch real metrics from GitHub API"""
        print("\nFetching real GitHub data...")

        # Fetch repositories
        repos = self._fetch_repositories()
        if not repos:
            print("No repositories found or error fetching repositories.")
            return self._create_sample_metrics()

        print(f"Found {len(repos)} repositories. Analyzing...")

        metrics_data = []
        analyzed_count = 0

        for repo in repos[:20]:  # Limit to 20 repos to avoid rate limits
            print(f"  Analyzing {repo}...")
            repo_metrics = self._calculate_metrics_for_repository(repo)
            if repo_metrics:
                metrics_data.append(repo_metrics)
                analyzed_count += 1

            # Rate limiting
            time.sleep(0.5)

        print(f"Successfully analyzed {analyzed_count} repositories.")
        return metrics_data

    def _fetch_repositories(self) -> List[str]:
        """Fetch all repositories in the organization"""
        if not self.github_token:
            return []

        url = f'{self.base_url}/orgs/{self.organization}/repos'
        params = {
            'per_page': 100,
            'sort': 'updated',
            'direction': 'desc'
        }

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            repos_data = response.json()

            # Filter out forks and archived repos
            repos = []
            for repo in repos_data:
                if not repo.get('fork', False) and not repo.get('archived', False):
                    repos.append(repo['name'])

            return repos[:50]  # Limit to 50 most recent active repos

        except requests.exceptions.RequestException as e:
            print(f"Error fetching repositories: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error: {e}")
            return []

    def _calculate_metrics_for_repository(self, repo_name: str) -> Optional[Dict]:
        """Calculate DORA metrics for a single repository"""
        try:
            # Fetch data from GitHub API
            deployments = self._fetch_repository_deployments(repo_name)
            workflow_runs = self._fetch_workflow_runs(repo_name)
            pull_requests = self._fetch_pull_requests(repo_name)

            # Calculate metrics
            deployment_frequency = self._calculate_deployment_frequency(
                deployments)
            lead_time_hours = self._calculate_lead_time(pull_requests)
            change_failure_rate = self._calculate_failure_rate(workflow_runs)
            time_to_restore_hours = self._calculate_time_to_restore(
                workflow_runs)

            # Create metrics dictionary
            metrics = {
                'deployment_frequency': deployment_frequency,
                'lead_time_hours': lead_time_hours,
                'change_failure_rate': change_failure_rate,
                'time_to_restore_hours': time_to_restore_hours
            }

            # Calculate performance level
            metrics['performance_level'] = self._calculate_performance_level(
                metrics)

            # Track data sources used
            data_sources = {
                'deployment_frequency': {
                    'method': 'deployments',
                    'count': len(deployments),
                    'valid': len(deployments) > 0
                },
                'lead_time': {
                    'method': 'pull_requests',
                    'count': len(pull_requests),
                    'valid': len(pull_requests) > 0
                },
                'change_failure_rate': {
                    'method': 'workflow_runs',
                    'count': len(workflow_runs),
                    'valid': len(workflow_runs) > 0
                },
                'time_to_restore': {
                    'method': 'workflow_runs',
                    'count': len(workflow_runs),
                    'valid': len(workflow_runs) > 0
                }
            }

            return {
                'repository': repo_name,
                'metrics': metrics,
                'data_sources': data_sources,
                'last_updated': datetime.now().isoformat(),
                'data_points': {
                    'deployments_analyzed': len(deployments),
                    'workflow_runs_analyzed': len(workflow_runs),
                    'pull_requests_analyzed': len(pull_requests),
                    'analysis_period_days': 30
                }
            }

        except Exception as e:
            print(f"  Error calculating metrics for {repo_name}: {e}")
            return None

    def _fetch_repository_deployments(self, repo: str, days: int = 30) -> List[Dict]:
        """Fetch deployment events for a repository"""
        if not self.github_token:
            return []

        url = f'{self.base_url}/repos/{self.organization}/{repo}/deployments'
        params = {
            'per_page': 100,
            'page': 1
        }

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            deployments = response.json()

            # Filter deployments from last N days
            cutoff_date = datetime.now() - timedelta(days=days)
            filtered_deployments = []

            for deployment in deployments:
                created_at = datetime.strptime(
                    deployment['created_at'], '%Y-%m-%dT%H:%M:%SZ')
                if created_at >= cutoff_date:
                    filtered_deployments.append(deployment)

            return filtered_deployments

        except Exception as e:
            print(f"  Warning: Could not fetch deployments for {repo}: {e}")
            return []

    def _fetch_workflow_runs(self, repo: str, days: int = 30) -> List[Dict]:
        """Fetch workflow runs to calculate failure rates"""
        if not self.github_token:
            return []

        url = f'{self.base_url}/repos/{self.organization}/{repo}/actions/runs'
        params = {
            'per_page': 100,
            'page': 1
        }

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            workflow_runs = data.get('workflow_runs', [])

            # Filter runs from last N days
            cutoff_date = datetime.now() - timedelta(days=days)
            filtered_runs = []

            for run in workflow_runs:
                created_at = datetime.strptime(
                    run['created_at'], '%Y-%m-%dT%H:%M:%SZ')
                if created_at >= cutoff_date:
                    filtered_runs.append(run)

            return filtered_runs

        except Exception as e:
            print(f"  Warning: Could not fetch workflow runs for {repo}: {e}")
            return []

    def _fetch_pull_requests(self, repo: str, days: int = 30) -> List[Dict]:
        """Fetch PRs to calculate lead time"""
        if not self.github_token:
            return []

        url = f'{self.base_url}/repos/{self.organization}/{repo}/pulls'
        params = {
            'state': 'closed',
            'sort': 'updated',
            'direction': 'desc',
            'per_page': 50
        }

        try:
            response = requests.get(
                url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            prs = response.json()

            # Filter PRs merged in last N days
            cutoff_date = datetime.now() - timedelta(days=days)
            filtered_prs = []

            for pr in prs:
                if pr.get('merged_at'):
                    merged_at = datetime.strptime(
                        pr['merged_at'], '%Y-%m-%dT%H:%M:%SZ')
                    if merged_at >= cutoff_date:
                        filtered_prs.append(pr)

            return filtered_prs[:20]  # Limit to 20 most recent PRs

        except Exception as e:
            print(f"  Warning: Could not fetch PRs for {repo}: {e}")
            return []

    def _calculate_deployment_frequency(self, deployments: List[Dict]) -> str:
        """Calculate deployment frequency category"""
        if not deployments:
            return 'MONTHLY'

        deployment_count = len(deployments)

        if deployment_count >= 30:  # ~daily
            return 'DAILY'
        elif deployment_count >= 8:  # ~2x per week
            return 'WEEKLY'
        elif deployment_count >= 4:  # ~weekly
            return 'WEEKLY'
        else:
            return 'MONTHLY'

    def _calculate_lead_time(self, prs: List[Dict]) -> float:
        """Calculate average lead time in hours from PR creation to merge"""
        if not prs:
            return 48.0  # Default value

        lead_times = []
        for pr in prs:
            created_at = datetime.strptime(
                pr['created_at'], '%Y-%m-%dT%H:%M:%SZ')
            merged_at = datetime.strptime(
                pr['merged_at'], '%Y-%m-%dT%H:%M:%SZ')
            lead_time_hours = (merged_at - created_at).total_seconds() / 3600

            # Filter out extreme outliers (e.g., PRs open for months)
            if lead_time_hours <= 720:  # 30 days max
                lead_times.append(lead_time_hours)

        if lead_times:
            return sum(lead_times) / len(lead_times)
        return 48.0  # Default fallback

    def _calculate_failure_rate(self, workflow_runs: List[Dict]) -> float:
        """Calculate change failure rate percentage"""
        if not workflow_runs:
            return 20.0  # Default value

        total_runs = len(workflow_runs)
        failed_runs = len(
            [run for run in workflow_runs if run.get('conclusion') == 'failure'])

        if total_runs == 0:
            return 20.0

        return (failed_runs / total_runs) * 100

    def _calculate_time_to_restore(self, workflow_runs: List[Dict]) -> float:
        """Calculate time to restore from failed runs"""
        if not workflow_runs:
            return 12.0  # Default value

        # Sort runs by creation time
        sorted_runs = sorted(workflow_runs, key=lambda x: x['created_at'])

        restore_times = []

        for i, run in enumerate(sorted_runs):
            if run.get('conclusion') == 'failure':
                failure_time = datetime.strptime(
                    run['created_at'], '%Y-%m-%dT%H:%M:%SZ')

                # Find next successful run
                for next_run in sorted_runs[i+1:]:
                    if next_run.get('conclusion') == 'success':
                        success_time = datetime.strptime(
                            next_run['created_at'], '%Y-%m-%dT%H:%M:%SZ')
                        restore_time = (
                            success_time - failure_time).total_seconds() / 3600

                        # Only consider reasonable restore times (max 48 hours)
                        if restore_time <= 48:
                            restore_times.append(restore_time)
                        break

        if restore_times:
            return sum(restore_times) / len(restore_times)

        return 12.0  # Default fallback

    def _calculate_performance_level(self, metrics: Dict) -> str:
        """Calculate DORA performance level based on metrics"""
        deployment_freq = metrics.get('deployment_frequency', '').upper()
        lead_time = metrics.get('lead_time_hours', float('inf'))
        failure_rate = metrics.get('change_failure_rate', float('inf'))
        restore_time = metrics.get('time_to_restore_hours', float('inf'))

        # Elite criteria
        if (deployment_freq in ['DAILY', 'ON_DEMAND'] and
            lead_time <= 1 and
            failure_rate <= 15 and
                restore_time <= 1):
            return 'ELITE'

        # High criteria
        elif (deployment_freq in ['WEEKLY', 'DAILY', 'ON_DEMAND'] and
              lead_time <= 24 and
              failure_rate <= 30 and
              restore_time <= 24):
            return 'HIGH'

        # Low criteria
        else:
            return 'LOW'

    def _create_sample_metrics(self) -> List[Dict]:
        """Create realistic sample metrics data (fallback when no GitHub token)"""
        import random

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

            metrics['performance_level'] = self._calculate_performance_level(
                metrics)

            # Generate realistic data source counts
            deployments_count = random.randint(
                5, 50) if deployment_freq == 'DAILY' else random.randint(2, 20)
            workflow_runs_count = random.randint(20, 200)
            prs_count = random.randint(5, 40)

            metrics_data.append({
                'repository': repo,
                'metrics': metrics,
                'data_sources': {
                    'deployment_frequency': {
                        'method': 'deployments',
                        'count': deployments_count,
                        'valid': deployments_count > 0
                    },
                    'lead_time': {
                        'method': 'pull_requests',
                        'count': prs_count,
                        'valid': prs_count > 0
                    },
                    'change_failure_rate': {
                        'method': 'workflow_runs',
                        'count': workflow_runs_count,
                        'valid': workflow_runs_count > 0
                    },
                    'time_to_restore': {
                        'method': 'workflow_runs',
                        'count': workflow_runs_count,
                        'valid': workflow_runs_count > 0
                    }
                },
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
            csv_path = os.path.join(self.visualizer.output_dir,
                                    f'dora_metrics_summary_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
            df.to_csv(csv_path, index=False)
            print(f"  Created metrics table: {os.path.basename(csv_path)}")

            # Save as Excel
            try:
                excel_path = os.path.join(self.visualizer.output_dir,
                                          f'dora_metrics_summary_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
                df.to_excel(excel_path, index=False, engine='openpyxl')
                print(
                    f"  Created Excel report: {os.path.basename(excel_path)}")
            except ImportError:
                print("  Note: Install openpyxl for Excel export: pip install openpyxl")
            except Exception as e:
                print(f"  Error creating Excel file: {e}")

    def _generate_windows_compatible_html(self, metrics_data: List[Dict], dashboard_path: str):
        """Generate HTML report compatible with Windows encoding with trending theme"""
        # Convert main dashboard image to base64
        try:
            with open(dashboard_path, 'rb') as img_file:
                img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
        except Exception as e:
            print(f"  Warning: Could not encode dashboard image: {e}")
            img_base64 = ""

        # Collect individual repository report images
        repo_images = {}
        for repo in metrics_data:
            if 'metrics' in repo:
                repo_name = repo['repository']
                # Try to find the individual report image
                report_pattern = f"dora_report_{repo_name.replace('/', '_')}_*.png"
                report_files = []
                
                # Look in reports directory
                reports_dir = self.visualizer.output_dir
                for filename in os.listdir(reports_dir):
                    if filename.startswith(f"dora_report_{repo_name.replace('/', '_')}_") and filename.endswith('.png'):
                        report_files.append(filename)
                
                # Use the most recent one if multiple exist
                if report_files:
                    # Sort by date (most recent first)
                    report_files.sort(reverse=True)
                    report_path = os.path.join(reports_dir, report_files[0])
                    try:
                        with open(report_path, 'rb') as img_file:
                            repo_images[repo_name] = base64.b64encode(img_file.read()).decode('utf-8')
                    except Exception as e:
                        print(f"  Warning: Could not encode report image for {repo_name}: {e}")
                        repo_images[repo_name] = None
                else:
                    repo_images[repo_name] = None

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
                <h3>Organizations: {self.organization}</h3>
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
            
            <div class="dashboard-container">
    """

        if img_base64:
            html_content += f"""
                <div class="image-container">
                    <img class="dashboard-img" src="data:image/png;base64,{img_base64}" 
                        alt="DORA Metrics Dashboard" id="mainDashboard">
                    <div class="zoom-icon" onclick="openModal('mainDashboard')">
                        🔍
                    </div>
                </div>
                <a href="data:image/png;base64,{img_base64}" download="dora_main_dashboard.png" 
                class="download-btn">📥 Download Dashboard</a>
    """

        html_content += f"""
            </div>
            
            <!-- Individual Repository Dashboards -->
            <div class="section-header">
                <h3>🏢 Individual Repository Reports</h3>
            </div>
            
            <div class="repo-dashboards-grid">
    """

        # Add individual repository dashboards
        for i, repo in enumerate(metrics_data):
            if 'metrics' in repo:
                repo_name = repo['repository']
                metrics = repo['metrics']
                perf_class = metrics['performance_level'].lower()
                img_base64_repo = repo_images.get(repo_name)
                
                html_content += f"""
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
                
                if img_base64_repo:
                    html_content += f"""
                    <div class="image-container">
                        <img class="dashboard-img" src="data:image/png;base64,{img_base64_repo}" 
                            alt="DORA Report - {repo_name}" id="repoDashboard{i}">
                        <div class="zoom-icon" onclick="openModal('repoDashboard{i}')">
                            🔍
                        </div>
                    </div>
                    <a href="data:image/png;base64,{img_base64_repo}" download="dora_report_{repo_name}.png" 
                    class="download-btn">📥 Download {repo_name} Report</a>
    """
                else:
                    html_content += """
                    <div style="background: #f1f5f9; padding: 40px; border-radius: 10px; text-align: center;">
                        <div style="font-size: 1.2em; color: #64748b; margin-bottom: 10px;">
                            📊 Individual report not available
                        </div>
                        <div style="font-size: 0.9em; color: #94a3b8;">
                            The detailed report for this repository could not be loaded.
                        </div>
                    </div>
    """
                
                html_content += """
                </div>
    """

        html_content += f"""
            </div>
            
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
                avg_metrics['total_deployments'] += data_points.get('deployments_analyzed', 0)
                avg_metrics['total_workflow_runs'] += data_points.get('workflow_runs_analyzed', 0)
                avg_metrics['total_prs'] += data_points.get('pull_requests_analyzed', 0)
        
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
            
            <!-- Insights Grid -->
            <div class="section-header">
                <h3>💡 Actionable Insights & Recommendations</h3>
            </div>
            
            <div class="insights-grid">
                <div class="insight-card">
                    <h4>🎯 Optimization Focus</h4>
                    <ul style="margin: 0; padding-left: 20px; color: #475569;">
    """

        # Dynamic insights based on metrics
        if avg_metrics['lead_time'] > 24:
            html_content += '<li>🚨 <strong>Critical:</strong> Reduce lead time through CI/CD pipeline optimization</li>'
        elif avg_metrics['lead_time'] > 8:
            html_content += '<li>⚠️ <strong>Opportunity:</strong> Streamline code review and deployment processes</li>'
        else:
            html_content += '<li>✅ <strong>Strength:</strong> Lead time is within optimal range</li>'
            
        if avg_metrics['failure_rate'] > 20:
            html_content += '<li>⚠️ <strong>High Priority:</strong> Improve test coverage and deployment validation</li>'
        elif avg_metrics['failure_rate'] > 10:
            html_content += '<li>📊 <strong>Monitor:</strong> Failure rate is acceptable but can be improved</li>'
        else:
            html_content += '<li>✅ <strong>Strength:</strong> Change failure rate is excellent</li>'
            
        elite_percentage = (avg_metrics['elite_count'] / max(repo_count, 1)) * 100
        if elite_percentage < 30:
            html_content += f'<li>📈 <strong>Goal:</strong> Increase Elite repositories from {elite_percentage:.0f}% to 50%+</li>'
        else:
            html_content += f'<li>🎉 <strong>Success:</strong> {elite_percentage:.0f}% of repositories are Elite performers</li>'

        html_content += """
                    </ul>
                </div>
                
                <div class="insight-card">
                    <h4>🚀 Quick Wins</h4>
                    <ul style="margin: 0; padding-left: 20px; color: #475569;">
                        <li>Implement automated deployment rollbacks</li>
                        <li>Add real-time deployment monitoring</li>
                        <li>Create deployment playbooks for common scenarios</li>
                        <li>Set up automated performance alerts</li>
                        <li>Standardize CI/CD templates across teams</li>
                    </ul>
                </div>
                
                <div class="insight-card">
                    <h4>📈 Growth Opportunities</h4>
                    <ul style="margin: 0; padding-left: 20px; color: #475569;">
                        <li>Adopt feature flag deployment strategies</li>
                        <li>Implement canary deployments for risk reduction</li>
                        <li>Establish cross-team DevOps communities</li>
                        <li>Invest in developer self-service tooling</li>
                        <li>Create DORA metrics dashboards for each team</li>
                    </ul>
                </div>
            </div>
            
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
        html_path = os.path.join(self.visualizer.output_dir,
                                f'dora_report_{self.organization}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html')

        try:
            # Try UTF-8 first
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
        except UnicodeEncodeError:
            # Fallback to ASCII with errors ignored
            with open(html_path, 'w', encoding='ascii', errors='ignore') as f:
                f.write(html_content)
            print("  Note: Some characters were omitted for Windows compatibility")

        print(f"  Created trending dashboard report: {os.path.basename(html_path)}")
        return html_path

    def generate_text_report(self, metrics_data: List[Dict]):
        """Generate a simple text report for Windows compatibility"""
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
"""

        text_path = os.path.join(self.visualizer.output_dir,
                                 f'dora_report_{self.organization}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')

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
        dora = DORAFrameworkFixed(org)
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