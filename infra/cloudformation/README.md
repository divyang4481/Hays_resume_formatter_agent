# AWS CloudFormation Infrastructure & Deployment Guide

This directory contains the AWS CloudFormation templates and deployment scripts to provision the complete infrastructure for the Hays Resume Formatter Agent on AWS.

---

## 1. Directory Structure

- **[hay-agent-infra.yaml](hay-agent-infra.yaml)**: (Part 1) Provisions core database and storage: S3 bucket, SQS main processing queue, dead letter queue (DLQ), RDS PostgreSQL database instance, and related security groups.
- **[ecs-infra.yaml](ecs-infra.yaml)**: (Part 3) Provisions runtime container compute: Application Load Balancer (ALB), ECS Fargate Cluster, Task Definitions, and Services for API, Worker, and Frontend.
- **[parameters-example.json](parameters-example.json)** & **[parameters-hay-agent-example.json](parameters-hay-agent-example.json)**: Example Parameter files to pass custom properties to the CloudFormation templates.
- **[deploy-aws.ps1](../../scripts/deploy-aws.ps1)**: The PowerShell orchestration script automating build, ECR registry upload, stack deployment, environment syncing, and task scaling.

---

## 2. Option A: Deployment Using the PowerShell Script (Recommended)

The PowerShell script `scripts/deploy-aws.ps1` automates all steps, parses your local `.env` file, builds container images, and pushes them to ECR.

### Prerequisites

1. Ensure your AWS CLI is authenticated to the target account.
2. Verify Docker Desktop is running locally.
3. Make sure a local `.env` file is present in the project root.

### Example A.1: Deploy Everything (Parts 1, 2, and 3)

Runs through all resource provisioning, image builds, and task starts:

```powershell
.\scripts\deploy-aws.ps1 -Action DeployAll -DBPassword "HaysResumeAgent123!"
```

### Example A.2: Deploy Only Core Resources (S3, SQS, RDS)

Useful if you only want to provision the database and storage:

```powershell
.\scripts\deploy-aws.ps1 -Action DeployInfra -DBPassword "YourSecurePassword123!"
```

### Example A.3: Build & Push Images to ECR

Creates repositories and builds local images to push them up:

```powershell
.\scripts\deploy-aws.ps1 -Action DeployEcr
```

### Example A.4: Deploy/Update ECS Tasks & Load Balancer

Reads RDS endpoint & bucket outputs and launches ECS Task Definitions:

```powershell
.\scripts\deploy-aws.ps1 -Action DeployEcs -DBPassword "YourSecurePassword123!"
```

### Example A.5: Scale Services up or down (desired count 0 or 1)

Allows stopping and starting containers without deleting any resources:

```powershell
# Stop Worker container
.\scripts\deploy-aws.ps1 -Action Scale -ServiceToScale worker -DesiredCount 0

# Start Worker container
.\scripts\deploy-aws.ps1 -Action Scale -ServiceToScale worker -DesiredCount 1

# Stop API container
.\scripts\deploy-aws.ps1 -Action Scale -ServiceToScale api -DesiredCount 0
```

---

## 3. Option B: Manual Step-by-Step Deployment (Raw AWS CLI)

If you prefer deploying the templates step-by-step using raw AWS CLI commands, follow this guide:

### Step 3.1: Deploy Core Infra (Part 1)

Provisions S3, SQS, and RDS instance inside VPC `vpc-77ca851f` and subnets `subnet-0fbd1d43,subnet-4c26e037`:

```powershell
aws cloudformation deploy `
  --template-file infra/cloudformation/hay-agent-infra.yaml `
  --stack-name hay-agent-infra-dev `
  --parameter-overrides ProjectName="hay-agent" Environment="dev" VpcId="vpc-77ca851f" SubnetIds="subnet-0fbd1d43,subnet-4c26e037" DBPassword="YourSecurePassword123!" DBUsername="dbadmin" AllowedIngressCidr="0.0.0.0/0" `
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM `
  --region ap-south-1
```

### Step 3.2: Deploy ECR Repositories (Part 2)

```powershell
aws cloudformation deploy `
  --template-file cloudformation.yaml `
  --stack-name hay-agent-ecr-dev `
  --parameter-overrides ProjectName="hay-agent" Environment="dev" `
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM `
  --region ap-south-1
```

### Step 3.3: Docker Login, Build & Push

Retrieve the ECR repository URIs from ECR console or outputs, log in, and push the images:

```powershell
# ECR Login
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com

# Build Images
docker build -f docker/Dockerfile -t <AWS_ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-api-dev:latest .
docker build -f docker/Dockerfile -t <AWS_ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-worker-dev:latest .
docker build -f docker/Dockerfile.frontend -t <AWS_ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-frontend-dev:latest .

# Push Images
docker push <AWS_ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-api-dev:latest
docker push <AWS_ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-worker-dev:latest
docker push <AWS_ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-frontend-dev:latest
```

### Step 3.4: Deploy ECS Cluster, ALB & Services (Part 3)

Replace parameter values with the outputs from Step 3.1 and Step 3.2:

```powershell
aws cloudformation deploy `
  --template-file infra/cloudformation/ecs-infra.yaml `
  --stack-name hay-agent-ecs-dev `
  --parameter-overrides `
      ProjectName="hay-agent" `
      Environment="dev" `
      VpcId="vpc-77ca851f" `
      SubnetIds="subnet-0fbd1d43,subnet-4c26e037" `
      StorageBucketName="hay-agent-storage-dev-<AWS_ACCOUNT_ID>-ap-south-1" `
      SQSQueueArn="arn:aws:sqs:ap-south-1:<AWS_ACCOUNT_ID>:hay-agent-queue-dev" `
      SQSQueueUrl="https://sqs.ap-south-1.amazonaws.com/<AWS_ACCOUNT_ID>/hay-agent-queue-dev" `
      DatabaseUrl="postgresql+psycopg://dbadmin:YourSecurePassword123!@hay-agent-db-dev.<DB_IDENTIFIER>.ap-south-1.rds.amazonaws.com:5432/HayAgent" `
      ApiImageUri="<AWS_ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-api-dev:latest" `
      WorkerImageUri="<AWS_ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-worker-dev:latest" `
      FrontendImageUri="<AWS_ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-frontend-dev:latest" `
      ApiDesiredCount=1 `
      WorkerDesiredCount=1 `
      FrontendDesiredCount=1 `
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM `
  --region ap-south-1
```

Once deployed successfully, retrieve the `AlbDnsName` output value and open it in your web browser to access the application.
