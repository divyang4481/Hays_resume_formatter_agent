param(
  [string]$Region = "ap-south-1",
  [string]$Environment = "dev",
  [string]$ProjectName = "agentic-doc",
  [string]$StackName = "hays-resume-formatter-agent-ecr",
  [string]$Version = "v1.0.0",
  [string]$ApiRepositoryName = "agentic-doc-api-dev",
  [string]$WorkerRepositoryName = "agentic-doc-worker-dev",
  [string]$FrontendRepositoryName = "agentic-doc-frontend-dev",
  [switch]$CreateEcrRepositories
)

$ErrorActionPreference = "Stop"

Write-Host "[ECR] Verifying AWS identity..."
$identity = aws sts get-caller-identity --output json | ConvertFrom-Json
$accountId = $identity.Account
if (-not $accountId) { throw "Unable to resolve AWS account id." }

$registry = "$accountId.dkr.ecr.$Region.amazonaws.com"
$apiRepo = if ($ApiRepositoryName) { $ApiRepositoryName } else { "$ProjectName-api-$Environment" }
$workerRepo = if ($WorkerRepositoryName) { $WorkerRepositoryName } else { "$ProjectName-worker-$Environment" }
$frontendRepo = if ($FrontendRepositoryName) { $FrontendRepositoryName } else { "$ProjectName-frontend-$Environment" }

$apiImage = "$registry/$apiRepo"
$workerImage = "$registry/$workerRepo"
$frontendImage = "$registry/$frontendRepo"

if ($CreateEcrRepositories) {
  Write-Host "[ECR] Deploying/Updating ECR repositories stack: $StackName"
  aws cloudformation deploy `
    --stack-name $StackName `
    --template-file cloudformation.yaml `
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM `
    --parameter-overrides ProjectName=$ProjectName Environment=$Environment `
    --region $Region
}

Write-Host "[ECR] Verifying target repositories exist in $Region"
foreach ($repo in @($apiRepo, $workerRepo, $frontendRepo)) {
  aws ecr describe-repositories --repository-names $repo --region $Region | Out-Null
}

Write-Host "[ECR] Logging into ECR: $registry"
aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $registry

Write-Host "[Build] Building API image"
docker build -f docker/Dockerfile -t "${apiImage}:latest" -t "${apiImage}:$Version" .

Write-Host "[Build] Building Worker image"
docker build -f docker/Dockerfile -t "${workerImage}:latest" -t "${workerImage}:$Version" .

Write-Host "[Build] Building Frontend image"
docker build -f docker/Dockerfile.frontend -t "${frontendImage}:latest" -t "${frontendImage}:$Version" .

Write-Host "[Push] Pushing API image tags"
docker push "${apiImage}:latest"
docker push "${apiImage}:$Version"

Write-Host "[Push] Pushing Worker image tags"
docker push "${workerImage}:latest"
docker push "${workerImage}:$Version"

Write-Host "[Push] Pushing Frontend image tags"
docker push "${frontendImage}:latest"
docker push "${frontendImage}:$Version"

Write-Host "[Done] Images pushed:"
Write-Host "  - ${apiImage}:$Version"
Write-Host "  - ${workerImage}:$Version"
Write-Host "  - ${frontendImage}:$Version"
