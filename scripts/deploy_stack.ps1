param(
  [string]$StackName = "resume-formatteragent-2",
  [string]$Region = "ap-south-1",
  [string]$AllowedIngressCidr = "0.0.0.0/0",
  [string]$DBUsername = "appuser",
  [string]$DBPassword,
  [string]$DBName = "resume_agent",
  [string]$VpcCidr = "10.42.0.0/16",
  [string]$PublicSubnet1Cidr = "10.42.1.0/24",
  [string]$PublicSubnet2Cidr = "10.42.2.0/24"
)

if (-not $DBPassword) { throw "DBPassword is required" }

$TemplatePath = "infra/cloudformation/resume-formatter-v2.yaml"

$paramOverrides = @(
  "ProjectName=resume-formatteragent-2",
  "Environment=dev",
  "VpcCidr=$VpcCidr",
  "PublicSubnet1Cidr=$PublicSubnet1Cidr",
  "PublicSubnet2Cidr=$PublicSubnet2Cidr",
  "AllowedIngressCidr=$AllowedIngressCidr",
  "DBUsername=$DBUsername",
  "DBPassword=$DBPassword",
  "DBName=$DBName"
)

aws cloudformation deploy `
  --stack-name $StackName `
  --template-file $TemplatePath `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides $paramOverrides `
  --region $Region

aws cloudformation describe-stacks --stack-name $StackName --region $Region --query "Stacks[0].Outputs" --output table
