# AWS Deployment Guide

This guide contains the step-by-step instructions and commands to deploy the Hays Resume Formatter Agent infrastructure on AWS. Run these commands from your PowerShell console (with your python virtual environment `.venv` activated).

---

## Step 1: AWS Profile & Authentication Setup

Set your active AWS profile and region in your current PowerShell terminal session, and check that your session is authenticated:

```powershell
# 1. Set AWS profile and region in your active terminal session
$env:AWS_PROFILE="divyang"
$env:AWS_DEFAULT_REGION="ap-south-1"

# 2. Test/Verify your identity (outputs your AWS Account ID and ARN)
aws sts get-caller-identity
```

---

## Option A: Full Containerized ECS Fargate Deployment (Recommended)

This option uses the PowerShell orchestration script `scripts/deploy-aws.ps1` to build and upload API, Worker, and Frontend Docker containers, deploy network infrastructure, and spin up ECS Fargate tasks.

*Ensure Docker Desktop is running locally on your computer before executing.*

### 1. Deploy Everything (All Stack Parts, Docker Build, ECR Push & ECS Service Scaling)
```powershell
.\scripts\deploy-aws.ps1 -Action DeployAll -DBPassword "HaysAdmin123!#" -Region "ap-south-1" -ProjectName "hay-agent" -Environment "dev"
```

### 2. Deploy Sub-Actions Separately (Optional)

* **Deploy Core Infrastructure only** (VPC, RDS PostgreSQL Database, S3 Bucket, SQS Queue):
  ```powershell
  .\scripts\deploy-aws.ps1 -Action DeployInfra -DBPassword "HaysAdmin123!#" -Region "ap-south-1" -ProjectName "hay-agent" -Environment "dev"
  ```
* **Build & Push Docker Images to ECR only**:
  ```powershell
  .\scripts\deploy-aws.ps1 -Action DeployEcr -Region "ap-south-1" -ProjectName "hay-agent" -Environment "dev"
  ```
* **Deploy ECS cluster, Task Definitions, Services, and ALB load balancer**:
  ```powershell
  .\scripts\deploy-aws.ps1 -Action DeployEcs -DBPassword "HaysAdmin123!#" -Region "ap-south-1" -ProjectName "hay-agent" -Environment "dev"
  ```

---

## Option B: Networking & Databases Stack Only (No Containers)

This option deploys the `resume-formatter-v2.yaml` template (containing S3, SQS, RDS, and VPC settings) and then automatically generates/updates your local `.env` file with the deployed resources' details.

### 1. Deploy the Core CloudFormation Stack
```powershell
.\scripts\deploy_stack.ps1 -StackName "resume-formatteragent-2" -Region "ap-south-1" -DBUsername "appuser" -DBPassword "HaysAdmin123!#" -DBName "resume_agent"
```

### 2. Sync Deployed Stack Outputs to `.env`
Run this script to retrieve the database host, queue URLs, and S3 bucket from AWS, then automatically configure your local `.env` file:
```powershell
.\scripts\stack_to_env.ps1 -StackName "resume-formatteragent-2" -Region "ap-south-1" -DBUsername "appuser" -DBPassword "HaysAdmin123!#" -AWSProfile "divyang"
```

---

## Option C: Raw AWS CLI & Docker Commands (Manual Steps)

If you prefer not to use the helper PowerShell scripts, you can run these raw commands to deploy in your preferred order:

### 1. Build Local Docker Images
Before pushing, build the three applications locally:
```powershell
docker build -f docker/Dockerfile -t hay-agent-api-dev:latest .
docker build -f docker/Dockerfile -t hay-agent-worker-dev:latest .
docker build -f docker/Dockerfile.frontend -t hay-agent-frontend-dev:latest .
```

### 2. Create ECR Repositories (Part 2) if not created already
```powershell
aws cloudformation deploy `
  --template-file cloudformation.yaml `
  --stack-name hay-agent-ecr-dev `
  --parameter-overrides ProjectName="hay-agent" Environment="dev" `
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM `
  --region ap-south-1
```

### 3. Log In, Tag, and Push Docker Images to ECR
*(Uses your verified account ID `114644266543`)*
```powershell
# 3.1. ECR Docker Login
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin 114644266543.dkr.ecr.ap-south-1.amazonaws.com

# 3.2. Tag local images with the remote ECR repository URIs
docker tag hay-agent-api-dev:latest 114644266543.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-api-dev:latest
docker tag hay-agent-worker-dev:latest 114644266543.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-worker-dev:latest
docker tag hay-agent-frontend-dev:latest 114644266543.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-frontend-dev:latest

# 3.3. Push images to ECR
docker push 114644266543.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-api-dev:latest
docker push 114644266543.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-worker-dev:latest
docker push 114644266543.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-frontend-dev:latest
```

### 4. Create Core Infrastructure Stack (Part 1 - S3, SQS, RDS PostgreSQL)
```powershell
aws cloudformation deploy `
  --template-file infra/cloudformation/hay-agent-infra.yaml `
  --stack-name hay-agent-infra-dev `
  --parameter-overrides ProjectName="hay-agent" Environment="dev" VpcId="vpc-77ca851f" SubnetIds="subnet-0fbd1d43,subnet-4c26e037" DBPassword="HaysAdmin123!#" DBUsername="dbadmin" AllowedIngressCidr="0.0.0.0/0" `
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM `
  --region ap-south-1
```

### 5. Deploy ECS Cluster, ALB & Services (Part 3)
Retrieve the outputs from Step 4 and Step 2 to populate these fields.
*(Replace `<DB_IDENTIFIER>` with your RDS DB instance host URL sub-domain identifier from Step 4)*
```powershell
aws cloudformation deploy `
  --template-file infra/cloudformation/ecs-infra.yaml `
  --stack-name hay-agent-ecs-dev `
  --parameter-overrides `
      ProjectName="hay-agent" `
      Environment="dev" `
      VpcId="vpc-77ca851f" `
      SubnetIds="subnet-0fbd1d43,subnet-4c26e037" `
      StorageBucketName="hay-agent-storage-dev-114644266543-ap-south-1" `
      SQSQueueArn="arn:aws:sqs:ap-south-1:114644266543:hay-agent-queue-dev" `
      SQSQueueUrl="https://sqs.ap-south-1.amazonaws.com/114644266543/hay-agent-queue-dev" `
      DatabaseUrl="postgresql+psycopg://dbadmin:HaysAdmin123!#@hay-agent-db-dev.<DB_IDENTIFIER>.ap-south-1.rds.amazonaws.com:5432/HayAgent" `
      ApiImageUri="114644266543.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-api-dev:latest" `
      WorkerImageUri="114644266543.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-worker-dev:latest" `
      FrontendImageUri="114644266543.dkr.ecr.ap-south-1.amazonaws.com/hay-agent-frontend-dev:latest" `
      ApiDesiredCount=1 `
      WorkerDesiredCount=1 `
      FrontendDesiredCount=1 `
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM `
  --region ap-south-1
```
