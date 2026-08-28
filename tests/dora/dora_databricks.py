# dorm_framework.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests
import os
from enum import Enum

class DatabricksDORAMetrics(Enum):
    """Databricks-specific DORA metrics categories"""
    JOB_FREQUENCY = "job_execution_frequency"
    DATA_LEAD_TIME = "data_pipeline_lead_time"
    PIPELINE_FAILURE_RATE = "pipeline_failure_rate"
    JOB_RESTORE_TIME = "job_restore_time"
    COST_PER_RUN = "cost_per_job_run"
    CLUSTER_UTILIZATION = "cluster_utilization"
    DATA_FRESHNESS = "data_freshness"
    QUALITY_FAILURE_RATE = "data_quality_failure_rate"

@dataclass
class DatabricksJobMetrics:
    """Metrics for Databricks jobs"""
    job_id: str
    job_name: str
    deployment_frequency: str  # DAILY/WEEKLY/MONTHLY
    lead_time_hours: float     # Data to insight time
    failure_rate: float        # % Job failure percentage
    restore_time_hours: float  # Time to fix failed jobs
    cost_per_run: float        # Estimated cost per execution
    cluster_utilization: float # % Cluster CPU/Memory usage
    data_freshness_hours: float# Time since last successful run
    data_quality_score: float  # Data quality metric (0-100)
    
    @property
    def performance_level(self) -> str:
        """Calculate performance level for Databricks jobs"""
        if (self.deployment_frequency == "DAILY" and
            self.lead_time_hours < 1 and
            self.failure_rate < 10 and
            self.data_freshness_hours < 1):
            return "ELITE"
        elif (self.deployment_frequency in ["DAILY", "WEEKLY"] and
              self.lead_time_hours < 24 and
              self.failure_rate < 20 and
              self.data_freshness_hours < 24):
            return "HIGH"
        else:
            return "LOW"

class DatabricksDORMCollector:
    """Collect DORA metrics from Databricks jobs"""
    
    def __init__(self, databricks_host: str, token: str):
        self.host = databricks_host.rstrip('/')
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def get_jobs_list(self, limit: int = 25) -> List[Dict]:
        """Get list of all jobs in workspace"""
        url = f"{self.host}/api/2.1/jobs/list"
        params = {"limit": limit}
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json().get("jobs", [])
        except Exception as e:
            print(f"Error fetching jobs: {e}")
            return []
    
    def get_job_runs(self, job_id: int, days: int = 30) -> List[Dict]:
        """Get job runs for specific job"""
        url = f"{self.host}/api/2.1/jobs/runs/list"
        params = {
            "job_id": job_id,
            "limit": 25,
            "start_time": int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json().get("runs", [])
        except Exception as e:
            print(f"Error fetching job runs for {job_id}: {e}")
            return []
    
    def get_run_details(self, run_id: int) -> Optional[Dict]:
        """Get detailed run information"""
        url = f"{self.host}/api/2.1/jobs/runs/get"
        params = {"run_id": run_id}
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching run details {run_id}: {e}")
            return None
    
    def calculate_job_frequency(self, runs: List[Dict]) -> str:
        """Calculate job execution frequency"""
        if not runs:
            return "MONTHLY"
        
        run_count = len(runs)
        days_analyzed = 30  # Default analysis period
        
        runs_per_day = run_count / days_analyzed
        
        if runs_per_day >= 1:
            return "DAILY"
        elif runs_per_day >= 0.14:  # Once per week
            return "WEEKLY"
        else:
            return "MONTHLY"
    
    def calculate_lead_time(self, runs: List[Dict]) -> float:
        """Calculate lead time for data jobs"""
        if not runs:
            return 24.0  # Default
        
        successful_runs = [r for r in runs if r.get("state", {}).get("result_state") == "SUCCESS"]
        
        if not successful_runs:
            return 24.0
        
        # Calculate average time from schedule to completion
        lead_times = []
        for run in successful_runs[:10]:  # Last 10 successful runs
            start_time = run.get("start_time", 0)
            end_time = run.get("end_time", 0)
            
            if start_time and end_time:
                duration_ms = end_time - start_time
                duration_hours = duration_ms / (1000 * 60 * 60)
                lead_times.append(duration_hours)
        
        return sum(lead_times) / len(lead_times) if lead_times else 24.0
    
    def calculate_failure_rate(self, runs: List[Dict]) -> float:
        """Calculate job failure rate"""
        if not runs:
            return 0.0
        
        failed_runs = len([r for r in runs if r.get("state", {}).get("result_state") == "FAILED"])
        total_runs = len(runs)
        
        return (failed_runs / total_runs) * 100 if total_runs > 0 else 0.0
    
    def calculate_restore_time(self, runs: List[Dict]) -> float:
        """Calculate time to restore failed jobs"""
        failed_runs = [r for r in runs if r.get("state", {}).get("result_state") == "FAILED"]
        
        if not failed_runs or len(failed_runs) < 2:
            return 12.0  # Default
        
        # Sort by time
        sorted_failed = sorted(failed_runs, key=lambda x: x.get("start_time", 0))
        
        restore_times = []
        for i in range(len(sorted_failed) - 1):
            current_failure = sorted_failed[i]
            next_success = self._find_next_successful_run(runs, current_failure)
            
            if next_success:
                failure_end = current_failure.get("end_time", 0)
                success_start = next_success.get("start_time", 0)
                
                if failure_end and success_start:
                    restore_ms = success_start - failure_end
                    restore_hours = restore_ms / (1000 * 60 * 60)
                    
                    if restore_hours <= 48:  # Filter outliers
                        restore_times.append(restore_hours)
        
        return sum(restore_times) / len(restore_times) if restore_times else 12.0
    
    def calculate_cost_per_run(self, run_details: Dict) -> float:
        """Estimate cost per job run"""
        # Simplified cost calculation
        # In production, integrate with Databricks cost API
        cluster_spec = run_details.get("cluster_spec", {})
        
        # Estimate based on cluster type and runtime
        driver_node_type = cluster_spec.get("driver_node_type_id", "Standard_DS3_v2")
        worker_node_type = cluster_spec.get("node_type_id", "Standard_DS3_v2")
        num_workers = cluster_spec.get("num_workers", 2)
        duration_ms = run_details.get("execution_duration", 300000)  # 5 min default
        
        # Simplified pricing (example values)
        node_hourly_cost = {
            "Standard_DS3_v2": 0.30,
            "Standard_DS4_v2": 0.60,
            "Standard_DS5_v2": 1.20,
            "Memory_Optimized": 0.90
        }
        
        driver_cost = node_hourly_cost.get(driver_node_type, 0.30)
        worker_cost = node_hourly_cost.get(worker_node_type, 0.30)
        
        duration_hours = duration_ms / (1000 * 60 * 60)
        total_cost = (driver_cost + (worker_cost * num_workers)) * duration_hours
        
        return round(total_cost, 2)
    
    def _find_next_successful_run(self, runs: List[Dict], failed_run: Dict) -> Optional[Dict]:
        """Find next successful run after a failure"""
        failed_time = failed_run.get("start_time", 0)
        
        later_runs = [r for r in runs if r.get("start_time", 0) > failed_time]
        successful_later = [r for r in later_runs if r.get("state", {}).get("result_state") == "SUCCESS"]
        
        return sorted(successful_later, key=lambda x: x.get("start_time", 0))[0] if successful_later else None

class DORMAnalyzer:
    """Analyze Databricks jobs using DORA metrics"""
    
    def __init__(self, databricks_host: str, token: str):
        self.collector = DatabricksDORMCollector(databricks_host, token)
    
    def analyze_job(self, job: Dict) -> DatabricksJobMetrics:
        """Analyze a single job"""
        job_id = job.get("job_id")
        job_name = job.get("settings", {}).get("name", "Unknown")
        
        # Get job runs
        runs = self.collector.get_job_runs(job_id)
        
        # Calculate metrics
        deployment_frequency = self.collector.calculate_job_frequency(runs)
        lead_time_hours = self.collector.calculate_lead_time(runs)
        failure_rate = self.collector.calculate_failure_rate(runs)
        restore_time_hours = self.collector.calculate_restore_time(runs)
        
        # Get cost estimation (from latest successful run)
        cost_per_run = 0.0
        successful_runs = [r for r in runs if r.get("state", {}).get("result_state") == "SUCCESS"]
        if successful_runs:
            latest_success = successful_runs[0]
            run_details = self.collector.get_run_details(latest_success.get("run_id"))
            if run_details:
                cost_per_run = self.collector.calculate_cost_per_run(run_details)
        
        # Calculate data freshness
        data_freshness_hours = self._calculate_data_freshness(runs)
        
        # Estimate cluster utilization (simplified)
        cluster_utilization = self._estimate_cluster_utilization(runs)
        
        # Data quality score (placeholder - integrate with data quality tools)
        data_quality_score = self._estimate_data_quality(runs)
        
        return DatabricksJobMetrics(
            job_id=str(job_id),
            job_name=job_name,
            deployment_frequency=deployment_frequency,
            lead_time_hours=lead_time_hours,
            failure_rate=failure_rate,
            restore_time_hours=restore_time_hours,
            cost_per_run=cost_per_run,
            cluster_utilization=cluster_utilization,
            data_freshness_hours=data_freshness_hours,
            data_quality_score=data_quality_score
        )
    
    def analyze_all_jobs(self) -> List[DatabricksJobMetrics]:
        """Analyze all jobs in workspace"""
        jobs = self.collector.get_jobs_list()
        metrics_list = []
        
        print(f"Analyzing {len(jobs)} Databricks jobs...")
        
        for job in jobs[:20]:  # Limit for demo
            try:
                metrics = self.analyze_job(job)
                metrics_list.append(metrics)
                print(f"  ✓ Analyzed: {metrics.job_name}")
            except Exception as e:
                print(f"  ✗ Failed to analyze job: {e}")
                continue
        
        return metrics_list
    
    def _calculate_data_freshness(self, runs: List[Dict]) -> float:
        """Calculate data freshness (hours since last successful run)"""
        successful_runs = [r for r in runs if r.get("state", {}).get("result_state") == "SUCCESS"]
        
        if not successful_runs:
            return 168.0  # 1 week default
        
        latest_success = max(successful_runs, key=lambda x: x.get("end_time", 0))
        latest_time = latest_success.get("end_time", 0)
        
        if latest_time:
            hours_since = (datetime.now().timestamp() * 1000 - latest_time) / (1000 * 60 * 60)
            return round(hours_since, 1)
        
        return 168.0
    
    def _estimate_cluster_utilization(self, runs: List[Dict]) -> float:
        """Estimate cluster utilization percentage"""
        if not runs:
            return 0.0
        
        # Simplified estimation
        successful_runs = [r for r in runs if r.get("state", {}).get("result_state") == "SUCCESS"]
        
        if not successful_runs:
            return 0.0
        
        # Calculate average runtime vs schedule interval
        total_runtime = sum(r.get("execution_duration", 0) for r in successful_runs)
        avg_runtime = total_runtime / len(successful_runs)
        
        # Assuming daily schedule
        daily_ms = 24 * 60 * 60 * 1000
        utilization = (avg_runtime / daily_ms) * 100
        
        return min(utilization, 100.0)  # Cap at 100%
    
    def _estimate_data_quality(self, runs: List[Dict]) -> float:
        """Estimate data quality score"""
        if not runs:
            return 100.0  # Default perfect score
        
        successful_runs = len([r for r in runs if r.get("state", {}).get("result_state") == "SUCCESS"])
        total_runs = len(runs)
        
        success_rate = (successful_runs / total_runs) * 100
        
        # Adjust for recent failures
        recent_runs = runs[:10]  # Last 10 runs
        recent_success = len([r for r in recent_runs if r.get("state", {}).get("result_state") == "SUCCESS"])
        recent_rate = (recent_success / len(recent_runs)) * 100 if recent_runs else 100
        
        # Weighted average favoring recent performance
        quality_score = (success_rate * 0.3) + (recent_rate * 0.7)
        
        return round(quality_score, 1)

# Example usage
def main():
    # Configuration
    DATABRICKS_HOST = os.getenv("DATABRICKS_HOST" )
    DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")
    
    if not DATABRICKS_TOKEN:
        print("Error: DATABRICKS_TOKEN environment variable is required")
        return
    
    # Initialize analyzer
    analyzer = DORMAnalyzer(DATABRICKS_HOST, DATABRICKS_TOKEN)
    
    # Analyze jobs
    print("🔍 Analyzing Databricks Jobs DORA Metrics...")
    metrics = analyzer.analyze_all_jobs()
    
    # Generate report
    print(f"\n📊 DORM Analysis Report")
    print("=" * 60)
    
    for job_metrics in metrics:
        print(f"\nJob: {job_metrics.job_name}")
        print(f"  Performance Level: {job_metrics.performance_level}")
        print(f"  Deployment Frequency: {job_metrics.deployment_frequency}")
        print(f"  Lead Time: {job_metrics.lead_time_hours:.1f} hours")
        print(f"  Failure Rate: {job_metrics.failure_rate:.1f}%")
        print(f"  Restore Time: {job_metrics.restore_time_hours:.1f} hours")
        print(f"  Cost per Run: ${job_metrics.cost_per_run:.2f}")
        print(f"  Data Freshness: {job_metrics.data_freshness_hours:.1f} hours")
        print(f"  Data Quality Score: {job_metrics.data_quality_score}/100")
    
    # Summary statistics
    elite_jobs = [m for m in metrics if m.performance_level == "ELITE"]
    high_jobs = [m for m in metrics if m.performance_level == "HIGH"]
    low_jobs = [m for m in metrics if m.performance_level == "LOW"]
    
    print(f"\n{'='*60}")
    print("📈 Summary Statistics")
    print(f"Total Jobs Analyzed: {len(metrics)}")
    print(f"Elite Jobs: {len(elite_jobs)} ({len(elite_jobs)/len(metrics)*100:.1f}%)")
    print(f"High Jobs: {len(high_jobs)} ({len(high_jobs)/len(metrics)*100:.1f}%)")
    print(f"Low Jobs: {len(low_jobs)} ({len(low_jobs)/len(metrics)*100:.1f}%)")
    
    # Cost analysis
    total_cost = sum(m.cost_per_run for m in metrics)
    avg_cost = total_cost / len(metrics) if metrics else 0
    print(f"\n💰 Cost Analysis")
    print(f"Estimated Total Run Cost: ${total_cost:.2f}")
    print(f"Average Cost per Job Run: ${avg_cost:.2f}")

if __name__ == "__main__":
    main()