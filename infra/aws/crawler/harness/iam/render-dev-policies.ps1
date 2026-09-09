[CmdletBinding()]
param(
    [string]$ProfileName = "inform-crawler-dev",
    [string]$AwsRegion = "ap-northeast-2",
    [string]$TerraformStateBucket = [Environment]::GetEnvironmentVariable(
        "INFORM_TFSTATE_BUCKET",
        "User"
    ),
    [string]$CrawlerStateBucket = [Environment]::GetEnvironmentVariable(
        "INFORM_CRAWLER_STATE_BUCKET",
        "User"
    ),
    [string]$VpcId = [Environment]::GetEnvironmentVariable("INFORM_VPC_ID", "User"),
    [string]$MainDbSecurityGroupId = [Environment]::GetEnvironmentVariable(
        "INFORM_MAIN_DB_SG_ID",
        "User"
    ),
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "rendered")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-ValueMatches {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [AllowEmptyString()]
        [string]$Value,
        [Parameter(Mandatory = $true)]
        [string]$Pattern
    )

    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -notmatch $Pattern) {
        throw "$Name is missing or invalid. Set its documented User environment variable."
    }
}

Assert-ValueMatches -Name "AWS Region" -Value $AwsRegion -Pattern '^[a-z]{2}-[a-z]+-\d$'
Assert-ValueMatches -Name "Terraform state bucket" -Value $TerraformStateBucket `
    -Pattern '^(?=.{3,63}$)[a-z0-9][a-z0-9.-]*[a-z0-9]$'
Assert-ValueMatches -Name "Crawler state bucket" -Value $CrawlerStateBucket `
    -Pattern '^(?=.{3,63}$)[a-z0-9][a-z0-9.-]*[a-z0-9]$'
Assert-ValueMatches -Name "VPC ID" -Value $VpcId -Pattern '^vpc-[0-9a-f]{8,17}$'
Assert-ValueMatches -Name "main DB Security Group ID" -Value $MainDbSecurityGroupId `
    -Pattern '^sg-[0-9a-f]{8,17}$'

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw "AWS CLI is not available on PATH."
}

$identityJson = & aws sts get-caller-identity --profile $ProfileName --output json
if ($LASTEXITCODE -ne 0) {
    throw "AWS STS identity lookup failed for the selected source profile."
}

$identity = $identityJson | ConvertFrom-Json
if ([string]$identity.Arn -notmatch '^arn:aws:iam::(?<accountId>\d{12}):user/(?<userPath>.+)$') {
    throw "The source profile must resolve to the existing IAM publisher user."
}

$accountId = $Matches.accountId
$publisherUserPath = $Matches.userPath
if ([string]$identity.Account -ne $accountId) {
    throw "STS Account and IAM user ARN account do not match."
}

$replacements = [ordered]@{
    "<AWS_ACCOUNT_ID>" = $accountId
    "<AWS_REGION>" = $AwsRegion
    "<ECR_PUBLISHER_USER_NAME>" = $publisherUserPath
    "<TERRAFORM_STATE_BUCKET>" = $TerraformStateBucket
    "<CRAWLER_STATE_BUCKET>" = $CrawlerStateBucket
    "<VPC_ID>" = $VpcId
    "<MAIN_DB_SECURITY_GROUP_ID>" = $MainDbSecurityGroupId
}

$templateNames = @(
    "publisher-assume-role-policy.json",
    "terraform-dev-role-trust-policy.json",
    "terraform-dev-role-permissions-policy.json"
)

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)

foreach ($templateName in $templateNames) {
    $templatePath = Join-Path $PSScriptRoot $templateName
    $content = [System.IO.File]::ReadAllText($templatePath)
    foreach ($entry in $replacements.GetEnumerator()) {
        $content = $content.Replace($entry.Key, $entry.Value)
    }

    if ($content -match '<[A-Z][A-Z0-9_]+>') {
        throw "Unresolved placeholder remains in $templateName."
    }
    $content | ConvertFrom-Json | Out-Null

    $outputName = $templateName.Replace(".json", ".rendered.json")
    $outputPath = Join-Path $OutputDirectory $outputName
    [System.IO.File]::WriteAllText($outputPath, $content, $utf8WithoutBom)
    Write-Output "Rendered policy: $outputPath"
}

Write-Output "No AWS resource was created or changed."
