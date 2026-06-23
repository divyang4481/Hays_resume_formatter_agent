param(
    [string]$ProjectName = "hay-agent",
    [string]$Environment = "dev",
    [string]$Region = "ap-south-1",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ecsStackName = "$ProjectName-ecs-$Environment"

Write-Host "==============================================" -ForegroundColor Yellow
Write-Host "WARNING: This will delete the ECS stack: $ecsStackName" -ForegroundColor Yellow
Write-Host "This will terminate all running ECS service tasks (API, Worker, Frontend)," -ForegroundColor Yellow
Write-Host "Application Load Balancer, Target Groups, and ECS Cluster associated with it." -ForegroundColor Yellow
Write-Host "==============================================" -ForegroundColor Yellow

if (-not $Force) {
    $confirmation = Read-Host -Prompt "Are you sure you want to delete stack '$ecsStackName'? (y/N)"
    if ($confirmation -ne "y" -and $confirmation -ne "yes") {
        Write-Host "Deletion cancelled by user." -ForegroundColor Gray
        exit 0
    }
}

Write-Host "[AWS] Verifying AWS Identity..."
$identity = aws sts get-caller-identity --output json | ConvertFrom-Json
$accountId = $identity.Account
if (-not $accountId) { throw "Unable to resolve AWS account ID from active profile." }

Write-Host "[Delete] Initiating delete-stack for '$ecsStackName' in region '$Region'..." -ForegroundColor Cyan
aws cloudformation delete-stack --stack-name $ecsStackName --region $Region

Write-Host "[Wait] Waiting for stack deletion to complete. This may take a few minutes..." -ForegroundColor Cyan
try {
    aws cloudformation wait stack-delete-complete --stack-name $ecsStackName --region $Region
    Write-Host "[Success] Stack '$ecsStackName' has been successfully deleted!" -ForegroundColor Green
}
catch {
    Write-Host "[Error] Failed waiting for stack deletion, or stack deletion encountered errors." -ForegroundColor Red
    throw
}
