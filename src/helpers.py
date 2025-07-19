"""
Helper utilities for AWS operations
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List

import boto3


class AWSHelpers:
    """Common AWS operations helpers"""

    def __init__(self, session: boto3.Session = None):
        self.session = session or boto3.Session()

    def get_client(self, service: str, region: str = "us-east-1"):
        """Get AWS client for specified service"""
        return self.session.client(service, region_name=region)

    def get_cost_data(
        self, start_date: str, end_date: str, group_by: str = "SERVICE", granularity: str = "MONTHLY"
    ) -> Dict[str, Any]:
        """Get cost data from Cost Explorer"""
        ce = self.get_client("ce")
        return ce.get_cost_and_usage(
            TimePeriod={"Start": start_date, "End": end_date},
            Granularity=granularity,
            Metrics=["BlendedCost", "UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": group_by}],
        )

    def get_metrics(
        self,
        namespace: str,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        instance_id: str = None,
        period: int = 3600,
    ) -> Dict[str, Any]:
        """Get CloudWatch metrics"""
        cw = self.get_client("cloudwatch")
        dimensions = []
        if instance_id:
            dimensions = [{"Name": "InstanceId", "Value": instance_id}]

        return cw.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=start_time,
            EndTime=end_time,
            Period=period,
            Statistics=["Average", "Maximum", "Minimum"],
        )

    def list_instances(self, state: str = "running") -> List[Dict[str, Any]]:
        """List EC2 instances by state"""
        ec2 = self.get_client("ec2")
        response = ec2.describe_instances(Filters=[{"Name": "instance-state-name", "Values": [state]}])

        instances = []
        for reservation in response["Reservations"]:
            for instance in reservation["Instances"]:
                instances.append(
                    {
                        "instance_id": instance["InstanceId"],
                        "instance_type": instance["InstanceType"],
                        "state": instance["State"]["Name"],
                        "launch_time": instance["LaunchTime"].isoformat(),
                        "tags": instance.get("Tags", []),
                    }
                )
        return instances

    def get_service_cost_summary(self, start_date: str, end_date: str) -> Dict[str, float]:
        """Get simplified cost summary by service"""
        costs = self.get_cost_data(start_date, end_date, "SERVICE")
        summary = {}

        for time_period in costs["ResultsByTime"]:
            for group in time_period["Groups"]:
                service = group["Keys"][0]
                amount = float(group["Metrics"]["BlendedCost"]["Amount"])
                summary[service] = summary.get(service, 0) + amount

        return summary


class CostUtils:
    """Utilities for cost analysis"""

    @staticmethod
    def total_cost(cost_data: Dict[str, Any]) -> float:
        """Calculate total cost from cost data"""
        total = 0
        for time_period in cost_data["ResultsByTime"]:
            for group in time_period["Groups"]:
                amount = float(group["Metrics"]["BlendedCost"]["Amount"])
                total += amount
        return total

    @staticmethod
    def filter_by_service(cost_data: Dict[str, Any], service_name: str) -> List[Dict[str, Any]]:
        """Filter cost data by service name"""
        filtered = []
        for time_period in cost_data["ResultsByTime"]:
            for group in time_period["Groups"]:
                if service_name.lower() in group["Keys"][0].lower():
                    filtered.append(group)
        return filtered

    @staticmethod
    def calculate_trend(cost_data: Dict[str, Any]) -> str:
        """Calculate cost trend (increasing/decreasing/stable)"""
        if len(cost_data["ResultsByTime"]) < 2:
            return "insufficient_data"

        costs = []
        for time_period in cost_data["ResultsByTime"]:
            period_total = sum(float(group["Metrics"]["BlendedCost"]["Amount"]) for group in time_period["Groups"])
            costs.append(period_total)

        if len(costs) < 2:
            return "insufficient_data"

        latest = costs[-1]
        previous = costs[-2]

        if latest > previous * 1.1:
            return "increasing"
        elif latest < previous * 0.9:
            return "decreasing"
        else:
            return "stable"


class MonitoringUtils:
    """Utilities for monitoring and alerting"""

    def __init__(self, session: boto3.Session = None):
        self.session = session or boto3.Session()

    def check_instance_health(self, instance_id: str) -> Dict[str, Any]:
        """Check EC2 instance health"""
        ec2 = self.session.client("ec2")
        cw = self.session.client("cloudwatch")

        # Get instance details
        instances = ec2.describe_instances(InstanceIds=[instance_id])
        instance = instances["Reservations"][0]["Instances"][0]

        # Get recent CPU metrics
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)

        metrics = cw.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName="CPUUtilization",
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=300,  # 5 minutes
            Statistics=["Average"],
        )

        avg_cpu = 0
        if metrics["Datapoints"]:
            avg_cpu = sum(point["Average"] for point in metrics["Datapoints"]) / len(metrics["Datapoints"])

        return {
            "instance_id": instance_id,
            "state": instance["State"]["Name"],
            "instance_type": instance["InstanceType"],
            "avg_cpu_last_hour": round(avg_cpu, 2),
            "status": "healthy" if avg_cpu < 90 else "high_cpu",
        }
