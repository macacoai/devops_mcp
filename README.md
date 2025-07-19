# AWS DevOps MCP Server

A powerful Model Context Protocol (MCP) server that provides low-level tools for AWS operations using boto3 and Pulumi, with a personal function management system.

## Features

### 🔧 Low-Level Tools

- **boto3_execute**: Execute arbitrary boto3 Python code with smart context imports
- **pulumi_preview**: Preview Pulumi infrastructure changes
- **pulumi_up**: Deploy Pulumi infrastructure

### 📚 Function Management

- **save_function**: Save reusable Python functions (max 20)
- **list_functions**: List saved functions with filtering
- **delete_function**: Delete saved functions
- **execute_with_functions**: Execute code with access to saved functions

### 🧠 Smart Features

- Context-aware imports (finops, devops, security)
- Helper utilities for common AWS operations
- Function usage tracking and statistics
- Persistent SQLite storage

## Quick Start

### Prerequisites

- Docker and Docker Compose
- AWS credentials configured
- (Optional) Pulumi account for infrastructure operations

### 1. Clone and Setup

```bash
git clone <repository>
cd aws_mcp
```

### 2. Configure Environment

```bash
# Copy environment template
cp env.example .env

# Edit .env with your configuration
# AWS_DEFAULT_REGION=us-east-1
# PULUMI_ACCESS_TOKEN=your_token_here
```

### 3. Start the Server

```bash
# Build and start the MCP server
docker-compose up -d aws-mcp-server

# View logs
docker-compose logs -f aws-mcp-server

# Alternative: Run with CLI arguments
docker run -it --rm \
  -v ~/.aws:/home/mcpuser/.aws:ro \
  -v ~/.pulumi:/home/mcpuser/.pulumi \
  -v $(pwd)/data:/app/data \
  aws-mcp-server \
  --aws-region us-west-2 \
  --max-functions 50 \
  --debug
```

### 4. Test the Installation

```bash
# Run the test suite
python examples/test_functions.py
```

## Usage Examples

### Basic boto3 Operations

```python
# Tool: boto3_execute
{
  "code": """
# List EC2 instances using helpers
instances = aws.list_instances('running')
print(f"Running instances: {len(instances)}")

for instance in instances[:3]:
    print(f"- {instance['instance_id']}: {instance['instance_type']}")
""",
  "context": "devops"
}
```

### FinOps Cost Analysis

```python
# Tool: boto3_execute
{
  "code": """
# Analyze monthly costs
costs = aws.get_service_cost_summary('2024-01-01', '2024-01-31')
total = sum(costs.values())

print(f"Total monthly cost: ${total:.2f}")
print("Top 5 services:")
for service, cost in sorted(costs.items(), key=lambda x: x[1], reverse=True)[:5]:
    print(f"- {service}: ${cost:.2f}")
""",
  "context": "finops"
}
```

### Infrastructure with Pulumi

```python
# Tool: pulumi_preview
{
  "code": """
import pulumi_aws as aws

# Create VPC
vpc = aws.ec2.Vpc("main-vpc",
    cidr_block="10.0.0.0/16",
    enable_dns_hostnames=True,
    tags={"Name": "main-vpc"})

# Create public subnet
subnet = aws.ec2.Subnet("public-subnet",
    vpc_id=vpc.id,
    cidr_block="10.0.1.0/24",
    availability_zone="us-east-1a",
    map_public_ip_on_launch=True)

pulumi.export("vpc_id", vpc.id)
pulumi.export("subnet_id", subnet.id)
""",
  "stack_name": "infrastructure",
  "project_name": "my-project"
}
```

### Save and Use Custom Functions

```python
# Tool: save_function
{
  "name": "get_cost_by_team",
  "code": """
def get_cost_by_team(team_name, start_date, end_date):
    \"\"\"Get costs for a specific team using tags\"\"\"
    costs = aws.get_cost_data(start_date, end_date)

    # Filter by team tag (simplified example)
    team_costs = []
    for period in costs['ResultsByTime']:
        for group in period['Groups']:
            # In real usage, you'd filter by tags
            team_costs.append(group)

    return cost.total_cost({'ResultsByTime': [{'Groups': team_costs}]})
""",
  "description": "Calculate costs for a specific team",
  "tags": ["finops", "teams"],
  "category": "cost_analysis"
}

# Then use it:
# Tool: execute_with_functions
{
  "code": """
team_cost = get_cost_by_team('frontend', '2024-01-01', '2024-01-31')
print(f"Frontend team cost: ${team_cost:.2f}")
""",
  "context": "finops"
}
```

## Architecture

```
aws_mcp/
├── src/
│   ├── mcp_server.py      # Main MCP server
│   ├── storage.py         # SQLite function storage
│   └── helpers.py         # AWS utility helpers
├── examples/
│   └── test_functions.py  # Test and demo script
├── data/                  # SQLite database storage
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Helper Utilities

The server includes pre-loaded helper utilities to reduce code repetition:

### AWSHelpers

- `aws.get_client(service, region)` - Quick client setup
- `aws.get_cost_data(start, end, group_by)` - Cost Explorer queries
- `aws.get_metrics(namespace, metric, start, end)` - CloudWatch metrics
- `aws.list_instances(state)` - List EC2 instances
- `aws.get_service_cost_summary(start, end)` - Cost summary by service

### CostUtils

- `cost.total_cost(cost_data)` - Calculate total from cost data
- `cost.filter_by_service(cost_data, service)` - Filter by service
- `cost.calculate_trend(cost_data)` - Calculate cost trend

### MonitoringUtils

- `monitoring.check_instance_health(instance_id)` - EC2 health check

## Configuration

### Command-Line Arguments

The server supports extensive command-line configuration. See [CLI_USAGE.md](CLI_USAGE.md) for complete documentation.

```bash
# Basic usage
python src/mcp_server.py --help

# AWS Configuration
python src/mcp_server.py --aws-region us-west-2 --aws-profile production

# Server Configuration  
python src/mcp_server.py --max-functions 50 --debug --database-path /tmp/functions.db

# Security Configuration
python src/mcp_server.py --enable-pulumi --enable-function-storage --execution-timeout 600

# Complete example
python src/mcp_server.py \
  --aws-region us-west-2 \
  --aws-profile production \
  --max-functions 50 \
  --debug \
  --execution-timeout 600 \
  --database-path /app/data/functions.db
```

#### Available Arguments

**AWS Configuration:**
- `--aws-region`, `--region` - AWS region (default: us-east-1)
- `--aws-profile`, `--profile` - AWS CLI profile
- `--aws-access-key-id` - AWS Access Key ID
- `--aws-secret-access-key` - AWS Secret Access Key

**Pulumi Configuration:**
- `--pulumi-token` - Pulumi access token
- `--pulumi-backend-url` - Pulumi backend URL

**Server Configuration:**
- `--database-path`, `--db-path` - Function storage database path
- `--max-functions` - Maximum functions to store (default: 20)
- `--debug` - Enable debug mode
- `--execution-timeout` - Code execution timeout in seconds (default: 300)

**Security Configuration:**
- `--enable-pulumi` - Enable Pulumi operations (default: true)
- `--enable-function-storage` - Enable function storage (default: true) 
- `--enable-boto3-execution` - Enable boto3 execution (default: true)

**Cost Analysis:**
- `--cost-analysis-days` - Default analysis period (default: 30)
- `--cost-alert-threshold` - Cost alert threshold in USD (default: 100)

### Environment Variables (Fallback)

All CLI arguments can also be set via environment variables:

```bash
# AWS Configuration
AWS_DEFAULT_REGION=us-east-1
AWS_PROFILE=default

# Pulumi Configuration
PULUMI_ACCESS_TOKEN=your_token
PULUMI_CONFIG_PASSPHRASE=your_passphrase

# MCP Configuration
MCP_SERVER_NAME=aws-devops-mcp
MCP_SERVER_VERSION=1.0.0
```

### Volume Mounts

- `~/.aws:/home/mcpuser/.aws:ro` - AWS credentials
- `~/.pulumi:/home/mcpuser/.pulumi` - Pulumi config
- `./data:/app/data` - Function database persistence
- `./src:/app/src` - Source code for development

## Function Management

### Limits and Features

- Maximum 20 saved functions per server
- Automatic syntax validation
- Usage tracking and statistics
- Function versioning support
- Category and tag filtering
- Persistent SQLite storage

### Function Categories

- `cost_analysis` - FinOps and cost management
- `monitoring` - Health checks and alerting
- `infrastructure` - Resource management
- `security` - Security and compliance
- `general` - General utilities

## Development

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run server locally
cd src
python mcp_server.py

# Run tests
python examples/test_functions.py
```

### Adding New Helpers

Edit `src/helpers.py` to add new utility functions that will be available in the execution namespace.

### Extending Tools

Add new MCP tools in `src/mcp_server.py` by following the existing pattern.

## Security Considerations

- Functions are executed in a controlled namespace
- No file system access from executed code
- AWS credentials should be properly scoped
- Consider using IAM roles with minimal permissions
- SQLite database is stored in mounted volume

## Troubleshooting

### Common Issues

1. **AWS Credentials**: Ensure AWS credentials are properly mounted and have necessary permissions
2. **Pulumi Token**: Set PULUMI_ACCESS_TOKEN environment variable
3. **Function Limit**: Delete unused functions if hitting the 20-function limit
4. **Syntax Errors**: Functions are validated on save, check error messages

### Debugging

```bash
# View server logs
docker-compose logs aws-mcp-server

# Connect to container for debugging
docker-compose exec aws-mcp-server /bin/bash

# Test function storage
sqlite3 data/functions.db ".tables"
```

## License

MIT License - see LICENSE file for details.
