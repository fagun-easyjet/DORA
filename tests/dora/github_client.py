# github_client.py
import requests
from typing import List
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time
from dotenv import load_dotenv

# Load variables from a .env file (if present) into the process environment.
# Safe to call even if no .env file exists, and safe to call multiple times -
# it won't override variables that are already set in the real environment.
load_dotenv()


class GitHubClient:
    """GitHub API client for DORA metrics collection"""

    def __init__(self, token: str = None, organization: str = "easyjet-dev"):
        # Never hardcode credentials. Pass explicitly or set GITHUB_TOKEN in the environment / .env file.
        self.token = os.getenv('GITHUB_FINE_TOKEN')
        if not self.token:
            raise ValueError("GITHUB_FINE_TOKEN environment variable is not set")
        else:
            self.organization = organization
            self.base_url = 'https://api.github.com'

            if self.token:
                self.headers = {
                    'Authorization': f'token {self.token}',
                    'Accept': 'application/vnd.github.v3+json',
                    'X-GitHub-Api-Version': '2022-11-28'
                }
            else:
                self.headers = {}

            self.session = requests.Session()
            self.session.headers.update(self.headers)

    def is_authenticated(self) -> bool:
        """Check if client is properly authenticated"""
        return bool(self.token) and 'Authorization' in self.session.headers

    # def fetch_repositories(self, limit: int = 50, exclude_forks: bool = True, exclude_archived: bool = True) -> List[str]:
    #     """Fetch all repositories in the organization"""
    #     if not self.is_authenticated():
    #         return []

    #     url = f'{self.base_url}/orgs/{self.organization}/repos'
    #     params = {
    #         'per_page': 100,
    #         'sort': 'updated',
    #         'direction': 'desc'
    #     }

    #     try:
    #         response = self.session.get(url, params=params, timeout=30)
    #         response.raise_for_status()
    #         repos_data = response.json()

    #         # Filter repositories
    #         repos = []
    #         for repo in repos_data:
    #             if exclude_forks and repo.get('fork', False):
    #                 continue
    #             if exclude_archived and repo.get('archived', False):
    #                 continue
    #             repos.append(repo['name'])

    #         return repos[:limit]  # Limit to specified number of repos

    #     except requests.exceptions.RequestException as e:
    #         print(f"Error fetching repositories: {e}")
    #         return []
    #     except Exception as e:
    #         print(f"Unexpected error: {e}")
    #         return []

    def fetch_repositories(
        self,
        limit: int = 50,
        exclude_forks: bool = False,
        exclude_archived: bool = True
    ) -> List[str]:

        if not self.is_authenticated():
            print("GitHub authentication failed.")
            return []

        url = f"{self.base_url}/orgs/{self.organization}/repos"

        repos = []
        page = 1

        try:
            while True:
                params = {
                    "per_page": 100,
                    "page": page,
                    "sort": "updated",
                    "direction": "desc",
                    "type": "all"
                }

                response = self.session.get(
                    url,
                    params=params,
                    timeout=30
                )
                response.raise_for_status()

                repos_data = response.json()

                # No more repositories
                if not repos_data:
                    break

                for repo in repos_data:

                    # Skip forks if requested
                    if exclude_forks and repo.get("fork", False):
                        continue

                    # Skip archived repositories if requested
                    if exclude_archived and repo.get("archived", False):
                        continue

                    repos.append(repo["name"])

                    # Stop when limit reached
                    if len(repos) >= limit:
                        print(f"Retrieved {len(repos)} repositories.")
                        return repos

                page += 1

            print(f"Retrieved {len(repos)} repositories.")
            return repos

        except requests.exceptions.HTTPError as e:
            print(
                f"HTTP Error fetching repositories: "
                f"{e.response.status_code} - {e.response.text}"
            )
            return []

        except requests.exceptions.RequestException as e:
            print(f"Error fetching repositories: {e}")
            return []

        except Exception as e:
            print(f"Unexpected error: {e}")
            return []

    def fetch_repository_deployments(self, repo_name: str, days: int = 30) -> List[Dict]:
        """Fetch deployment events for a repository"""
        if not self.is_authenticated():
            return []

        url = f'{self.base_url}/repos/{self.organization}/{repo_name}/deployments'
        params = {
            'per_page': 100,
            'page': 1
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
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
            print(f"Warning: Could not fetch deployments for {repo_name}: {e}")
            return []

    def fetch_workflow_runs(self, repo_name: str, days: int = 30) -> List[Dict]:
        """Fetch workflow runs to calculate failure rates"""
        if not self.is_authenticated():
            return []

        url = f'{self.base_url}/repos/{self.organization}/{repo_name}/actions/runs'
        params = {
            'per_page': 100,
            'page': 1
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
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
            print(
                f"Warning: Could not fetch workflow runs for {repo_name}: {e}")
            return []

    def fetch_pull_requests(self, repo_name: str, days: int = 30, limit: int = 20) -> List[Dict]:
        """Fetch PRs to calculate lead time"""
        if not self.is_authenticated():
            return []

        url = f'{self.base_url}/repos/{self.organization}/{repo_name}/pulls'
        params = {
            'state': 'closed',
            'sort': 'updated',
            'direction': 'desc',
            'per_page': 50
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
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

            return filtered_prs[:limit]  # Limit to specified number of PRs

        except Exception as e:
            print(f"Warning: Could not fetch PRs for {repo_name}: {e}")
            return []

    def get_repository_metrics(self, repo_name: str, days: int = 30) -> Dict:
        """Get all metrics for a single repository"""
        print(f"  Analyzing {repo_name}...")

        # Fetch data from GitHub API
        deployments = self.fetch_repository_deployments(repo_name, days)
        workflow_runs = self.fetch_workflow_runs(repo_name, days)
        pull_requests = self.fetch_pull_requests(repo_name, days)

        # Add rate limiting delay
        time.sleep(0.5)

        return {
            'repository': repo_name,
            'deployments': deployments,
            'workflow_runs': workflow_runs,
            'pull_requests': pull_requests,
            'metrics_summary': {
                'deployments_count': len(deployments),
                'workflow_runs_count': len(workflow_runs),
                'pull_requests_count': len(pull_requests),
                'analysis_period_days': days
            }
        }

    def get_organization_info(self) -> Optional[Dict]:
        """Get organization information"""
        if not self.is_authenticated():
            return None

        url = f'{self.base_url}/orgs/{self.organization}'

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching organization info: {e}")
            return None

    def test_connection(self) -> bool:
        """Test GitHub API connection"""
        if not self.is_authenticated():
            return False

        try:
            url = f'{self.base_url}/rate_limit'
            response = self.session.get(url, timeout=10)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False