"""
AWS DevOps MCP Server
Provides low-level tools for boto3, pulumi operations and function management
"""

import argparse
import asyncio
import json
import os
import traceback
from contextlib import asynccontextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict, List

import boto3
import pulumi
import pulumi_aws as aws
from fastmcp import FastMCP
from pulumi import automation as auto

from helpers import AWSHelpers, CostUtils, MonitoringUtils
from pulumi_backend_manager import PulumiBackendManager
from storage import FunctionStorage


def parse_arguments():
    """Parse command-line arguments with environment variable fallbacks"""
    parser = argparse.ArgumentParser(
        description="AWS DevOps MCP Server - " "Provides low-level tools for AWS operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --region us-west-2 --profile production
  %(prog)s --max-functions 50 --debug
  %(prog)s --database-path /tmp/functions.db --aws-region eu-west-1

Environment Variables:
  All arguments can also be set via environment variables:
  AWS_DEFAULT_REGION, AWS_PROFILE, DATABASE_PATH, MAX_FUNCTIONS, etc.
        """,
    )

    # AWS Configuration
    aws_group = parser.add_argument_group("AWS Configuration")
    aws_group.add_argument(
        "--aws-region",
        "--region",
        default=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        help="AWS region (default: %(default)s, env: AWS_DEFAULT_REGION)",
    )
    aws_group.add_argument(
        "--aws-profile",
        "--profile",
        default=os.getenv("AWS_PROFILE"),
        help="AWS CLI profile to use (env: AWS_PROFILE)",
    )
    aws_group.add_argument(
        "--aws-access-key-id",
        default=os.getenv("AWS_ACCESS_KEY_ID"),
        help="AWS Access Key ID (env: AWS_ACCESS_KEY_ID)",
    )
    aws_group.add_argument(
        "--aws-secret-access-key",
        default=os.getenv("AWS_SECRET_ACCESS_KEY"),
        help="AWS Secret Access Key (env: AWS_SECRET_ACCESS_KEY)",
    )

    # Pulumi Configuration
    pulumi_group = parser.add_argument_group("Pulumi Configuration")
    pulumi_group.add_argument(
        "--pulumi-token",
        default=os.getenv("PULUMI_ACCESS_TOKEN"),
        help="Pulumi access token (env: PULUMI_ACCESS_TOKEN)",
    )
    pulumi_group.add_argument(
        "--pulumi-backend-url",
        default=os.getenv("PULUMI_BACKEND_URL"),
        help="Pulumi backend URL (env: PULUMI_BACKEND_URL)",
    )
    pulumi_group.add_argument(
        "--auto-create-pulumi-backend",
        action="store_true",
        default=os.getenv("AUTO_CREATE_PULUMI_BACKEND", "true").lower() in ("true", "1", "yes", "on"),
        help="Auto-create Pulumi backend if it doesn't exist "
        "(default: %(default)s, env: AUTO_CREATE_PULUMI_BACKEND)",
    )

    # Server Configuration
    server_group = parser.add_argument_group("Server Configuration")
    server_group.add_argument(
        "--database-path",
        "--db-path",
        default=os.getenv("DATABASE_PATH", "data/functions.db"),
        help="Path to function storage database " "(default: %(default)s, env: DATABASE_PATH)",
    )
    server_group.add_argument(
        "--max-functions",
        type=int,
        default=int(os.getenv("MAX_FUNCTIONS", "20")),
        help="Maximum number of functions to store " "(default: %(default)s, env: MAX_FUNCTIONS)",
    )
    server_group.add_argument(
        "--debug",
        action="store_true",
        default=os.getenv("DEBUG", "false").lower() in ("true", "1", "yes", "on"),
        help="Enable debug mode (env: DEBUG)",
    )
    server_group.add_argument(
        "--execution-timeout",
        type=int,
        default=int(os.getenv("EXECUTION_TIMEOUT", "300")),
        help="Code execution timeout in seconds " "(default: %(default)s, env: EXECUTION_TIMEOUT)",
    )

    # Security Configuration
    security_group = parser.add_argument_group("Security Configuration")
    security_group.add_argument(
        "--enable-pulumi",
        action="store_true",
        default=os.getenv("ENABLE_PULUMI_OPERATIONS", "true").lower() in ("true", "1", "yes", "on"),
        help="Enable Pulumi operations " "(default: %(default)s, env: ENABLE_PULUMI_OPERATIONS)",
    )
    security_group.add_argument(
        "--enable-function-storage",
        action="store_true",
        default=os.getenv("ENABLE_FUNCTION_STORAGE", "true").lower() in ("true", "1", "yes", "on"),
        help="Enable function storage " "(default: %(default)s, env: ENABLE_FUNCTION_STORAGE)",
    )
    security_group.add_argument(
        "--enable-boto3-execution",
        action="store_true",
        default=os.getenv("ENABLE_BOTO3_EXECUTION", "true").lower() in ("true", "1", "yes", "on"),
        help="Enable boto3 code execution " "(default: %(default)s, env: ENABLE_BOTO3_EXECUTION)",
    )

    # Cost Analysis Configuration
    cost_group = parser.add_argument_group("Cost Analysis Configuration")
    cost_group.add_argument(
        "--cost-analysis-days",
        type=int,
        default=int(os.getenv("COST_ANALYSIS_DEFAULT_DAYS", "30")),
        help="Default cost analysis period in days " "(default: %(default)s, env: COST_ANALYSIS_DEFAULT_DAYS)",
    )
    cost_group.add_argument(
        "--cost-alert-threshold",
        type=float,
        default=float(os.getenv("COST_ALERT_THRESHOLD", "100.0")),
        help="Cost threshold for alerts in USD " "(default: %(default)s, env: COST_ALERT_THRESHOLD)",
    )

    return parser.parse_args()


class AWSDevOpsMCPServer(FastMCP):
    """MCP Server for AWS DevOps operations"""

    def __init__(self, config=None):
        self.config = config or parse_arguments()

        # Print configuration if debug mode is enabled
        if self.config.debug:
            print("🐛 Debug mode enabled")
            print(f"📍 AWS Region: {self.config.aws_region}")
            print(f"👤 AWS Profile: {self.config.aws_profile or 'default'}")
            print(f"💾 Database Path: {self.config.database_path}")
            print(f"📊 Max Functions: {self.config.max_functions}")

        # Setup AWS session with configuration
        session_kwargs = {}
        if self.config.aws_profile:
            session_kwargs["profile_name"] = self.config.aws_profile
        if self.config.aws_region:
            session_kwargs["region_name"] = self.config.aws_region

        # Set AWS credentials if provided via arguments
        if self.config.aws_access_key_id and self.config.aws_secret_access_key:
            session_kwargs.update(
                {
                    "aws_access_key_id": self.config.aws_access_key_id,
                    "aws_secret_access_key": self.config.aws_secret_access_key,
                }
            )

        self.aws_session = boto3.Session(**session_kwargs)

        # Set Pulumi environment variables if provided
        if self.config.pulumi_token:
            os.environ["PULUMI_ACCESS_TOKEN"] = self.config.pulumi_token

        # Setup Pulumi backend with auto-creation if enabled
        if self.config.pulumi_backend_url:
            backend_manager = PulumiBackendManager(aws_session=self.aws_session, debug=self.config.debug)

            backend_result = backend_manager.setup_backend(
                self.config.pulumi_backend_url, auto_create=self.config.auto_create_pulumi_backend
            )

            if backend_result["success"]:
                os.environ["PULUMI_BACKEND_URL"] = self.config.pulumi_backend_url
                if self.config.debug:
                    print(f"🔧 Pulumi Backend: {backend_result['message']}")
                    if backend_result.get("created"):
                        print(f"✨ Backend created: " f"{backend_result.get('backend_type')}")
            else:
                error_msg = "❌ Pulumi backend setup failed: " f"{backend_result['error']}"
                if self.config.debug:
                    print(error_msg)
                    if "suggestion" in backend_result:
                        print(f"💡 Suggestion: " f"{backend_result['suggestion']}")
                # Continue without failing, but warn user
                print(f"⚠️ Warning: {error_msg}")

        # Define the lifespan context manager for startup events
        @asynccontextmanager
        async def lifespan(app: FastMCP):
            # This is the startup logic
            await self._setup_tools()
            yield
            # No shutdown logic needed for now

        # Initialize FastMCP server with the lifespan manager
        super().__init__(lifespan=lifespan)
        self.title = "AWS DevOps MCP Server"
        self.description = self.__doc__
        self.storage = FunctionStorage(self.config.database_path, max_functions=self.config.max_functions)
        self.aws_helpers = AWSHelpers(session=self.aws_session)
        self.cost_utils = CostUtils()
        self.monitoring_utils = MonitoringUtils()

    async def _setup_tools(self):
        """Setup MCP tools based on configuration"""
        # Register tools using FastMCP decorators
        if self.config.enable_boto3_execution:
            self.tool("boto3_execute")(self._boto3_execute)
        
        if self.config.enable_pulumi:
            self.tool("pulumi_preview")(self._pulumi_preview)
            self.tool("pulumi_up")(self._pulumi_up)
        
        if self.config.enable_function_storage:
            self.tool("save_function")(self._save_function)
            self.tool("list_functions")(self._list_functions)
            self.tool("delete_function")(self._delete_function)
            self.tool("execute_with_functions")(self._execute_with_functions)



    def run(self, host="0.0.0.0", port=8000):
        """Run the MCP server"""
        if self.config.debug:
            print(f"🚀 Starting AWS DevOps MCP Server at http://{host}:{port}")
            print(
                f"🔧 Tools enabled: "
                f"boto3={self.config.enable_boto3_execution}, "
                f"pulumi={self.config.enable_pulumi}, "
                f"functions={self.config.enable_function_storage}"
            )
        # Use FastMCP's built-in run method with HTTP transport
        # Force host to 0.0.0.0 to make it accessible from outside container
        self.run_http_async(host="0.0.0.0", port=port, log_level="info" if self.config.debug else "warning")


# Create the server instance at the module level for discovery by tools like fastmcp/uvicorn
config = parse_arguments()
server = AWSDevOpsMCPServer(config)


async def main():
    """Main entry point"""
    await server.run_http_async()


if __name__ == "__main__":
    asyncio.run(main())


if __name__ == "__main__":
    main()
