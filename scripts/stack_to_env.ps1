param(
  [string]$StackName = "resume-formatteragent-2",
  [string]$Region = "ap-south-1",
  [string]$DBUsername = "appuser",
  [string]$DBPassword = "ReplaceMe123!",
  [string]$LLMProvider = "bedrock",
  [string]$LLMModelFast = "anthropic.claude-3-5-haiku-20241022-v1:0",
  [string]$LLMModelStrong = "anthropic.claude-3-5-sonnet-20240620-v1:0",
  [string]$AWSProfile = "default",
  [string]$BedrockAgentId = "IUJ4II3JAI",
  [string]$BedrockAgentAliasId = "VYKEJ4BOMZ",
  [string]$BedrockKbId = ""
)

if (-not $DBPassword) { throw "DBPassword is required" }

$outputs = aws cloudformation describe-stacks --stack-name $StackName --region $Region --query "Stacks[0].Outputs" --output json | ConvertFrom-Json

$map = @{}
foreach ($o in $outputs) { $map[$o.OutputKey] = $o.OutputValue }

$bucket = $map["BucketName"]
$templateQueue = $map["TemplateAnalysisQueueUrl"]
$resumeQueue = $map["ResumeFormatQueueUrl"]
$dbHost = $map["DBEndpoint"]
$dbPort = $map["DBPort"]

if (-not $bucket) { $bucket = "" }
if (-not $templateQueue) { $templateQueue = "" }
if (-not $resumeQueue) { $resumeQueue = "" }
if (-not $dbHost) { $dbHost = "localhost" }
if (-not $dbPort) { $dbPort = "5432" }

$processingQueue = if ($templateQueue) { $templateQueue } else { $resumeQueue }

$dbUrl = "postgresql+psycopg://$($DBUsername):$($DBPassword)@$($dbHost):$($dbPort)/resume_agent"

$envText = @"
APP_ENV=dev
API_HOST=0.0.0.0
API_PORT=8000
USE_AWS_SERVICES=true

CLOUD_PROVIDER=aws
RUNTIME_MODE=aws
PROCESSING_MODE=async
QUEUE_PROVIDER=sqs
STORAGE_PROVIDER=s3
AGENT_PROVIDER=python_orchestrated
KNOWLEDGE_PROVIDER=bedrock_kb
LLM_BACKEND=aws_bedrock

AWS_REGION=$Region
AWS_PROFILE=$AWSProfile

S3_BUCKET=$bucket
S3_BUCKET_INPUT=$bucket
S3_BUCKET_OUTPUT=$bucket
SQS_TEMPLATE_ANALYSIS_QUEUE_URL=$templateQueue
SQS_RESUME_FORMAT_QUEUE_URL=$resumeQueue
SQS_PROCESSING_QUEUE_URL=$processingQueue
SQS_WAIT_TIME_SECONDS=10
SQS_VISIBILITY_TIMEOUT_SECONDS=120
DATABASE_URL=$dbUrl

LLM_PROVIDER=$LLMProvider
LLM_MODEL_FAST=$LLMModelFast
LLM_MODEL_STRONG=$LLMModelStrong
LLM_API_KEY=
BEDROCK_MODEL_ID=$LLMModelStrong
BEDROCK_AGENT_ID=$BedrockAgentId
BEDROCK_AGENT_ALIAS_ID=$BedrockAgentAliasId
BEDROCK_KB_ID=$BedrockKbId

AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_SESSION_TOKEN=

ENABLE_AUTH=false
"@

Set-Content -Path .env -Value $envText -Encoding UTF8
Write-Host ".env written from stack outputs"
