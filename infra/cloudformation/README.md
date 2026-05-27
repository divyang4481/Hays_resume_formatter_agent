# HayAgent Infrastructure Deployment Guide

This directory contains the AWS CloudFormation templates and parameters for deploying the Core Infrastructure (S3, SQS, RDS DB) required by the HayAgent platform.

---

## 1. Files Overview

- **[hay-agent-infra.yaml](hay-agent-infra.yaml)**: The CloudFormation template containing S3 bucket, SQS processing queues, and the RDS PostgreSQL instance. Integrates directly into your existing VPC network.
- **[parameters-hay-agent-example.json](parameters-hay-agent-example.json)**: The JSON parameter file populated with default properties matching the active `cv-architect` setup in `ap-south-1`.

---

## 2. Validation

To verify the template syntax before deploying:

```bash
aws cloudformation validate-template --template-body file://infra/cloudformation/hay-agent-infra.yaml
```

---

## 3. Deploy Stack

Deploy the stack to AWS using your configured credentials. Replace `YourSuperSecurePassword123!` with your preferred secure database password:

```powershell
aws cloudformation deploy `
  --template-file infra/cloudformation/hay-agent-infra.yaml `
  --stack-name hay-agent-infra-dev `
  --parameter-overrides DBPassword="HaysAdmin123!#" `
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM
```

---

## 4. Retrieve Outputs & Populate `.env`

Once the stack is successfully deployed, use the following commands to view outputs or format them directly for your local `.env` configuration file.

### View Outputs as a Table

```powershell
aws cloudformation describe-stacks `
  --stack-name hay-agent-infra-dev `
  --query "Stacks[0].Outputs[].{Key:OutputKey, Value:OutputValue}" `
  --output table
```

### Directly Generate `.env` File Strings

Run this PowerShell snippet in your console to print out environment variable configurations formatted exactly for copying-and-pasting into your `.env` file:

```powershell
$outputs = aws cloudformation describe-stacks --stack-name hay-agent-infra-dev --query "Stacks[0].Outputs" --output json | ConvertFrom-Json
Write-Output "### --- COPY TO YOUR .env FILE --- ###"
foreach ($o in $outputs) {
    if ($o.OutputKey -eq "DBEndpointAddress") {
        Write-Output "DATABASE_URL=postgresql+psycopg://dbadmin:<YOUR_DB_PASSWORD>@$($o.OutputValue):5432/HayAgent"
    } else {
        Write-Output "$($o.OutputKey.ToUpper())=$($o.OutputValue)"
    }
}
```
