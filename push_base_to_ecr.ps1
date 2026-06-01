param(
  [string]$Region = "ap-south-1",
  [string]$Environment = "dev",
  [string]$ProjectName = "agentic-doc",
  [string]$StackName = "hays-resume-formatter-agent-ecr",
  [string]$Version = "latest",
  [string]$BaseRepositoryName = "agentic-doc-base-dev",
  [switch]$CreateEcrRepositories,
  [switch]$CreateBaseRepository
)

$ErrorActionPreference = "Stop"

Write-Host "[ECR] Verifying AWS identity..."
$identity = aws sts get-caller-identity --output json | ConvertFrom-Json
$accountId = $identity.Account
if (-not $accountId) { throw "Unable to resolve AWS account id." }

$registry = "$accountId.dkr.ecr.$Region.amazonaws.com"
$baseRepo = if ($BaseRepositoryName) { $BaseRepositoryName } else { "$ProjectName-base-$Environment" }
$baseImage = "$registry/$baseRepo"

if ($CreateEcrRepositories) {
  Write-Host "[ECR] Deploying/Updating ECR repositories stack: $StackName"
  aws cloudformation deploy `
    --stack-name $StackName `
    --template-file cloudformation.yaml `
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM `
    --parameter-overrides ProjectName=$ProjectName Environment=$Environment `
    --region $Region
}

Write-Host "[ECR] Verifying base repository exists: $baseRepo"
aws ecr describe-repositories --repository-names $baseRepo --region $Region | Out-Null 2>$null
if ($LASTEXITCODE -ne 0) {
  if ($CreateBaseRepository) {
    Write-Host "[ECR] Base repository not found. Creating: $baseRepo"
    aws ecr create-repository --repository-name $baseRepo --region $Region | Out-Null
  }
  else {
    throw "Base repository '$baseRepo' not found in region '$Region'. Re-run with -CreateBaseRepository to create it."
  }
}

Write-Host "[ECR] Logging into ECR: $registry"
aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $registry

Write-Host "[Build] Building base image from docker/Dockerfile"
docker build -f docker/Dockerfile -t "${baseImage}:latest" -t "${baseImage}:$Version" .

Write-Host "[Push] Pushing base image tags"
docker push "${baseImage}:latest"
docker push "${baseImage}:$Version"

Write-Host "[Done] Base image pushed to $baseImage"
