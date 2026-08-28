"""
DORA Metrics Calculator
Handles all DORA metrics calculations from raw GitHub data
"""
from datetime import datetime
from typing import List, Dict, Optional


class DORAMetricsCalculator:
    """Calculates DORA metrics from raw GitHub data"""

    @staticmethod
    def calculate_dora_metrics_from_raw(raw_data: Dict) -> Optional[Dict]:
        """Calculate DORA metrics from raw GitHub data"""
        try:
            deployments = raw_data.get('deployments', [])
            workflow_runs = raw_data.get('workflow_runs', [])
            pull_requests = raw_data.get('pull_requests', [])

            # Calculate metrics
            deployment_frequency = DORAMetricsCalculator._calculate_deployment_frequency(deployments)
            lead_time_hours = DORAMetricsCalculator._calculate_lead_time(pull_requests)
            change_failure_rate = DORAMetricsCalculator._calculate_failure_rate(workflow_runs)
            time_to_restore_hours = DORAMetricsCalculator._calculate_time_to_restore(workflow_runs)

            # Create metrics dictionary
            metrics = {
                'deployment_frequency': deployment_frequency,
                'lead_time_hours': lead_time_hours,
                'change_failure_rate': change_failure_rate,
                'time_to_restore_hours': time_to_restore_hours
            }

            # Calculate performance level
            metrics['performance_level'] = DORAMetricsCalculator._calculate_performance_level(metrics)

            return {
                'repository': raw_data['repository'],
                'metrics': metrics,
                'data_sources': DORAMetricsCalculator._get_data_sources(deployments, workflow_runs, pull_requests),
                'last_updated': datetime.now().isoformat(),
                'data_points': {
                    'deployments_analyzed': len(deployments),
                    'workflow_runs_analyzed': len(workflow_runs),
                    'pull_requests_analyzed': len(pull_requests),
                    'analysis_period_days': 30
                }
            }

        except Exception as e:
            print(f"  Error calculating metrics for {raw_data.get('repository', 'unknown')}: {e}")
            return None

    @staticmethod
    def _calculate_deployment_frequency(deployments: List[Dict]) -> str:
        """Calculate deployment frequency category"""
        if not deployments:
            return 'MONTHLY'

        deployment_count = len(deployments)

        if deployment_count >= 30:  # ~daily
            return 'DAILY'
        elif deployment_count >= 4:  # ~weekly or more often
            return 'WEEKLY'
        else:
            return 'MONTHLY'

    @staticmethod
    def _calculate_lead_time(pull_requests: List[Dict]) -> float:
        """Calculate average lead time in hours from PR creation to merge"""
        if not pull_requests:
            return 48.0  # Default value

        lead_times = []
        for pr in pull_requests:
            created_at = datetime.strptime(pr['created_at'], '%Y-%m-%dT%H:%M:%SZ')
            merged_at = datetime.strptime(pr['merged_at'], '%Y-%m-%dT%H:%M:%SZ')
            lead_time_hours = (merged_at - created_at).total_seconds() / 3600

            # Filter out extreme outliers (e.g., PRs open for months)
            if lead_time_hours <= 720:  # 30 days max
                lead_times.append(lead_time_hours)

        if lead_times:
            return sum(lead_times) / len(lead_times)
        return 48.0  # Default fallback

    @staticmethod
    def _calculate_failure_rate(workflow_runs: List[Dict]) -> float:
        """Calculate change failure rate percentage"""
        if not workflow_runs:
            return 20.0  # Default value

        total_runs = len(workflow_runs)
        failed_runs = len(
            [run for run in workflow_runs if run.get('conclusion') == 'failure']
        )

        if total_runs == 0:
            return 20.0

        return (failed_runs / total_runs) * 100

    @staticmethod
    def _calculate_time_to_restore(workflow_runs: List[Dict]) -> float:
        """Calculate time to restore from failed runs"""
        if not workflow_runs:
            return 12.0  # Default value

        # Sort runs by creation time
        sorted_runs = sorted(workflow_runs, key=lambda x: x['created_at'])

        restore_times = []

        for i, run in enumerate(sorted_runs):
            if run.get('conclusion') == 'failure':
                failure_time = datetime.strptime(
                    run['created_at'], '%Y-%m-%dT%H:%M:%SZ'
                )

                # Find next successful run
                for next_run in sorted_runs[i+1:]:
                    if next_run.get('conclusion') == 'success':
                        success_time = datetime.strptime(
                            next_run['created_at'], '%Y-%m-%dT%H:%M:%SZ'
                        )
                        restore_time = (
                            success_time - failure_time
                        ).total_seconds() / 3600

                        # Only consider reasonable restore times (max 48 hours)
                        if restore_time <= 48:
                            restore_times.append(restore_time)
                        break

        if restore_times:
            return sum(restore_times) / len(restore_times)

        return 12.0  # Default fallback

    @staticmethod
    def _calculate_performance_level(metrics: Dict) -> str:
        """Calculate DORA performance level based on metrics"""
        deployment_freq = metrics.get('deployment_frequency', '').upper()
        lead_time = metrics.get('lead_time_hours', float('inf'))
        failure_rate = metrics.get('change_failure_rate', float('inf'))
        restore_time = metrics.get('time_to_restore_hours', float('inf'))

        # Elite criteria
        if (
            deployment_freq in ['DAILY', 'ON_DEMAND']
            and lead_time <= 1
            and failure_rate <= 15
            and restore_time <= 1
        ):
            return 'ELITE'

        # High criteria
        elif (
            deployment_freq in ['WEEKLY', 'DAILY', 'ON_DEMAND']
            and lead_time <= 24
            and failure_rate <= 30
            and restore_time <= 24
        ):
            return 'HIGH'

        # Low criteria
        else:
            return 'LOW'

    @staticmethod
    def _get_data_sources(deployments: List[Dict], workflow_runs: List[Dict], pull_requests: List[Dict]) -> Dict:
        """Get data sources information for the metrics"""
        return {
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