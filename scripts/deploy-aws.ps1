param(
  [ValidateSet("DeployAll", "DeployInfra", "DeployEcr", "DeployEcs", "Scale")]
  [string]$Action = "DeployAll",
  [string]$DBPassword,
  [string]$Region = "ap-south-1",
  [string]$ProjectName = "hay-agent",
  [string]$Environment = "dev",
  [string]$VpcId = "vpc-77ca851f",
  [string]$SubnetIds = "subnet-0fbd1d43,subnet-4c26e037",
  [string]$DBUsername = "dbadmin",
  [string]$AllowedIngressCidr = "0.0.0.0/0",
  [int]$ApiDesiredCount = 0,
  [int]$WorkerDesiredCount = 0,
  [int]$FrontendDesiredCount = 0,
  [string]$Version = "latest",
  [ValidateSet("api", "worker", "frontend")]
  [string]$ServiceToScale,
  [int]$DesiredCount = 1,
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

# Stack Names Configuration
$infraStackName = "$ProjectName-infra-$Environment"
$ecrStackName = "$ProjectName-ecr-$Environment"
$ecsStackName = "$ProjectName-ecs-$Environment"

# Parse local .env file helper
$envPath = Join-Path $PSScriptRoot "..\.env"
$envMap = @{}
if (Test-Path $envPath) {
    Write-Host "[Env] Loading local .env file..."
    Get-Content $envPath | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line -match "=") {
            $parts = $line -split "=", 2
            $key = $parts[0].Trim()
            $value = $parts[1].Trim().Trim('"').Trim("'")
            $envMap[$key] = $value
        }
    }
}

function Get-EnvVal {
    param(
        [string]$key,
        [string]$defaultVal
    )
    if ($envMap.ContainsKey($key)) {
        return $envMap[$key]
    }
    return $defaultVal
}

# Identity Check
Write-Host "[AWS] Verifying AWS Identity..."
$identity = aws sts get-caller-identity --output json | ConvertFrom-Json
$accountId = $identity.Account
if (-not $accountId) { throw "Unable to resolve AWS account ID from active profile." }
Write-Host "[AWS] Authenticated with AWS Account: $accountId in region: $Region"

# -------------------------------------------------------------
# PART 1: Deploy Core Infra (S3, SQS, RDS)
# -------------------------------------------------------------
function Deploy-Infra {
    Write-Host "`n========================================================"
    Write-Host "Part 1: Deploying Core Infrastructure Stack ($infraStackName)..."
    Write-Host "========================================================"
    
    # Try parsing password from local .env if not supplied
    if (-not $DBPassword) {
        if ($envMap.ContainsKey("DATABASE_URL")) {
            if ($envMap["DATABASE_URL"] -match "postgresql\+psycopg://[^:]+:([^@]+)@") {
                $DBPassword = [uri]::UnescapeDataString($Matches[1])
                Write-Host "[Env] Extracted DBPassword from local DATABASE_URL."
            }
        }
        if (-not $DBPassword) {
            $DBPassword = Read-Host -Prompt "Enter secure password for RDS PostgreSQL Master User (min 8 chars)"
        }
    }
    
    $infraTemplate = Join-Path $PSScriptRoot "..\infra\cloudformation\hay-agent-infra.yaml"
    Write-Host "[Deploy] Running aws cloudformation deploy..."
    aws cloudformation deploy `
      --template-file $infraTemplate `
      --stack-name $infraStackName `
      --parameter-overrides ProjectName=$ProjectName Environment=$Environment VpcId=$VpcId SubnetIds=$SubnetIds DBPassword=$DBPassword DBUsername=$DBUsername AllowedIngressCidr=$AllowedIngressCidr `
      --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM `
      --region $Region
}

# -------------------------------------------------------------
# PART 2: Deploy ECR & Push Images
# -------------------------------------------------------------
function Deploy-Ecr {
    Write-Host "`n========================================================"
    Write-Host "Part 2: Deploying ECR Repositories Stack ($ecrStackName)..."
    Write-Host "========================================================"
    
    $ecrTemplate = Join-Path $PSScriptRoot "..\cloudformation.yaml"
    Write-Host "[Deploy] Running aws cloudformation deploy for ECR Repositories..."
    aws cloudformation deploy `
      --template-file $ecrTemplate `
      --stack-name $ecrStackName `
      --parameter-overrides ProjectName=$ProjectName Environment=$Environment `
      --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM `
      --region $Region

    if ($SkipBuild) {
        Write-Host "[Build] -SkipBuild specified. Skipping docker build/push."
        return
    }

    # Fetch repository URIs
    $ecrOutputs = aws cloudformation describe-stacks --stack-name $ecrStackName --region $Region --query "Stacks[0].Outputs" --output json | ConvertFrom-Json
    $apiRepoUri = ($ecrOutputs | Where-Object { $_.OutputKey -eq "ApiRepositoryUri" }).OutputValue
    $workerRepoUri = ($ecrOutputs | Where-Object { $_.OutputKey -eq "WorkerRepositoryUri" }).OutputValue
    $frontendRepoUri = ($ecrOutputs | Where-Object { $_.OutputKey -eq "FrontendRepositoryUri" }).OutputValue

    # ECR Login
    $registry = "$accountId.dkr.ecr.$Region.amazonaws.com"
    Write-Host "[Build] Logging in to ECR: $registry..."
    aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $registry

    # Docker Build
    Write-Host "[Build] Building API container: $apiRepoUri..."
    docker build -f docker/Dockerfile -t "${apiRepoUri}:latest" -t "${apiRepoUri}:${Version}" .
    
    Write-Host "[Build] Building Worker container: $workerRepoUri..."
    docker build -f docker/Dockerfile -t "${workerRepoUri}:latest" -t "${workerRepoUri}:${Version}" .
    
    Write-Host "[Build] Building Frontend container: $frontendRepoUri..."
    docker build -f docker/Dockerfile.frontend -t "${frontendRepoUri}:latest" -t "${frontendRepoUri}:${Version}" .

    # Docker Push
    Write-Host "[Push] Pushing API image to ECR..."
    docker push "${apiRepoUri}:latest"
    docker push "${apiRepoUri}:${Version}"
    
    Write-Host "[Push] Pushing Worker image to ECR..."
    docker push "${workerRepoUri}:latest"
    docker push "${workerRepoUri}:${Version}"
    
    Write-Host "[Push] Pushing Frontend image to ECR..."
    docker push "${frontendRepoUri}:latest"
    docker push "${frontendRepoUri}:${Version}"

    Write-Host "[Push] All images successfully built and pushed to ECR."
}

# -------------------------------------------------------------
# PART 3: Deploy ECS (ALB, Task Def, Services)
# -------------------------------------------------------------
function Deploy-Ecs {
    Write-Host "`n========================================================"
    Write-Host "Part 3: Deploying ECS Services & Load Balancer Stack ($ecsStackName)..."
    Write-Host "========================================================"
    
    # Check if Core stack exists and get outputs
    Write-Host "[Deploy] Retrieving outputs from Core Infrastructure stack..."
    $infraOutputs = aws cloudformation describe-stacks --stack-name $infraStackName --region $Region --query "Stacks[0].Outputs" --output json | ConvertFrom-Json
    $storageBucket = ($infraOutputs | Where-Object { $_.OutputKey -eq "S3BucketName" }).OutputValue
    $sqsQueueUrl = ($infraOutputs | Where-Object { $_.OutputKey -eq "SQSQueueUrl" }).OutputValue
    $sqsQueueArn = ($infraOutputs | Where-Object { $_.OutputKey -eq "SQSQueueArn" }).OutputValue
    $dbEndpoint = ($infraOutputs | Where-Object { $_.OutputKey -eq "DBEndpointAddress" }).OutputValue
    $dbPort = ($infraOutputs | Where-Object { $_.OutputKey -eq "DBPort" }).OutputValue
    $dbName = ($infraOutputs | Where-Object { $_.OutputKey -eq "DBName" }).OutputValue
    
    # Resolve DB Password for DATABASE_URL parameter
    if (-not $DBPassword -and $envMap.ContainsKey("DATABASE_URL")) {
        if ($envMap["DATABASE_URL"] -match "postgresql\+psycopg://[^:]+:([^@]+)@") {
            $DBPassword = [uri]::UnescapeDataString($Matches[1])
        }
    }
    
    if (-not $DBPassword) {
        $DBPassword = Read-Host -Prompt "Enter secure password for RDS PostgreSQL Master User (matching stack parameter)"
    }
    
    $escapedPassword = [uri]::EscapeDataString($DBPassword)
    $databaseUrl = "postgresql+psycopg://${DBUsername}:${escapedPassword}@${dbEndpoint}:${dbPort}/${dbName}"
    
    # Check ECR stack and get image URIs
    Write-Host "[Deploy] Retrieving outputs from ECR Repositories stack..."
    $ecrOutputs = aws cloudformation describe-stacks --stack-name $ecrStackName --region $Region --query "Stacks[0].Outputs" --output json | ConvertFrom-Json
    $apiRepoUri = ($ecrOutputs | Where-Object { $_.OutputKey -eq "ApiRepositoryUri" }).OutputValue
    $workerRepoUri = ($ecrOutputs | Where-Object { $_.OutputKey -eq "WorkerRepositoryUri" }).OutputValue
    $frontendRepoUri = ($ecrOutputs | Where-Object { $_.OutputKey -eq "FrontendRepositoryUri" }).OutputValue
    
    $apiImage = "${apiRepoUri}:${Version}"
    $workerImage = "${workerRepoUri}:${Version}"
    $frontendImage = "${frontendRepoUri}:${Version}"
    
    # Resolve dynamic environment configurations from local .env or defaults
    $bedrockAgentId = Get-EnvVal "BEDROCK_AGENT_ID" ""
    $bedrockAgentAliasId = Get-EnvVal "BEDROCK_AGENT_ALIAS_ID" ""
    $bedrockKbId = Get-EnvVal "BEDROCK_KB_ID" ""
    $enableDocling = Get-EnvVal "ENABLE_DOCLING" "true"
    $enableTikaFallback = Get-EnvVal "ENABLE_TIKA_FALLBACK" "true"
    $enableGpuWorker = Get-EnvVal "ENABLE_GPU_WORKER" "false"
    $parserTimeoutSeconds = Get-EnvVal "PARSER_TIMEOUT_SECONDS" "300"
    $maxFileSizeMb = Get-EnvVal "MAX_FILE_SIZE_MB" "10"
    $llmBackend = Get-EnvVal "LLM_BACKEND" "aws_bedrock"
    $llmModelName = Get-EnvVal "LLM_MODEL_NAME" "meta.llama3-70b-instruct-v1:0"
    $bedrockTemplateAnalysisModelId = Get-EnvVal "BEDROCK_TEMPLATE_ANALYSIS_MODEL_ID" "qwen.qwen3-235b-a22b-2507-v1:0"
    $bedrockFallbackModelId = Get-EnvVal "BEDROCK_FALLBACK_MODEL_ID" "qwen.qwen3-235b-a22b-2507-v1:0"
    $llmProvider = Get-EnvVal "LLM_PROVIDER" "bedrock"
    $llmModelFast = Get-EnvVal "LLM_MODEL_FAST" "qwen.qwen3-235b-a22b-2507-v1:0"
    $llmModelStrong = Get-EnvVal "LLM_MODEL_STRONG" "qwen.qwen3-235b-a22b-2507-v1:0"
    $enableAuth = Get-EnvVal "ENABLE_AUTH" "false"
    $logLevel = Get-EnvVal "LOG_LEVEL" "INFO"

    $ecsTemplate = Join-Path $PSScriptRoot "..\infra\cloudformation\ecs-infra.yaml"
    
    $params = @(
        "ProjectName=$ProjectName",
        "Environment=$Environment",
        "VpcId=$VpcId",
        "SubnetIds=$SubnetIds",
        "StorageBucketName=$storageBucket",
        "SQSQueueArn=$sqsQueueArn",
        "SQSQueueUrl=$sqsQueueUrl",
        "DatabaseUrl=$databaseUrl",
        "ApiImageUri=$apiImage",
        "WorkerImageUri=$workerImage",
        "FrontendImageUri=$frontendImage",
        "ApiDesiredCount=$ApiDesiredCount",
        "WorkerDesiredCount=$WorkerDesiredCount",
        "FrontendDesiredCount=$FrontendDesiredCount",
        "BedrockAgentId=$bedrockAgentId",
        "BedrockAgentAliasId=$bedrockAgentAliasId",
        "BedrockKbId=$bedrockKbId",
        "EnableDocling=$enableDocling",
        "EnableTikaFallback=$enableTikaFallback",
        "EnableGpuWorker=$enableGpuWorker",
        "ParserTimeoutSeconds=$parserTimeoutSeconds",
        "MaxFileSizeMb=$maxFileSizeMb",
        "LlmBackend=$llmBackend",
        "LlmModelName=$llmModelName",
        "BedrockTemplateAnalysisModelId=$bedrockTemplateAnalysisModelId",
        "BedrockFallbackModelId=$bedrockFallbackModelId",
        "LlmProvider=$llmProvider",
        "LlmModelFast=$llmModelFast",
        "LlmModelStrong=$llmModelStrong",
        "EnableAuth=$enableAuth",
        "LogLevel=$logLevel"
    )
    
    Write-Host "[Deploy] Running aws cloudformation deploy..."
    aws cloudformation deploy `
      --template-file $ecsTemplate `
      --stack-name $ecsStackName `
      --parameter-overrides $params `
      --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM `
      --region $Region

    # Describe stack outputs to present application ALB DNS Name
    $ecsOutputs = aws cloudformation describe-stacks --stack-name $ecsStackName --region $Region --query "Stacks[0].Outputs" --output json | ConvertFrom-Json
    $albDns = ($ecsOutputs | Where-Object { $_.OutputKey -eq "AlbDnsName" }).OutputValue
    
    Write-Host "`n==========================================================================" -ForegroundColor Green
    Write-Host "Deployment Successful!" -ForegroundColor Green
    Write-Host "Access the Hays Resume Formatter Agent web application at:" -ForegroundColor Green
    Write-Host "http://$albDns" -ForegroundColor Cyan
    Write-Host "==========================================================================`n" -ForegroundColor Green
}

# -------------------------------------------------------------
# ACTION RUNNER
# -------------------------------------------------------------
switch ($Action) {
    "DeployAll" {
        Deploy-Infra
        Deploy-Ecr
        Deploy-Ecs
    }
    "DeployInfra" {
        Deploy-Infra
    }
    "DeployEcr" {
        Deploy-Ecr
    }
    "DeployEcs" {
        Deploy-Ecs
    }
    "Scale" {
        if (-not $ServiceToScale) {
            throw "Parameter -ServiceToScale is required when Action is 'Scale'."
        }
        $cluster = "$ProjectName-cluster-$Environment"
        $svcName = "$ProjectName-$ServiceToScale-$Environment"
        
        Write-Host "[Scale] Scaling ECS service: $svcName in cluster: $cluster to $DesiredCount tasks..."
        aws ecs update-service --cluster $cluster --service $svcName --desired-count $DesiredCount --region $Region
        Write-Host "[Scale] Service scale command sent. It may take a moment for tasks to spin up/down."
    }
}
