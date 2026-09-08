[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^\d{12}$')][string]$ExpectedAccountId,
    [Parameter(Mandatory)][string]$ExpectedRegion,
    [Parameter(Mandatory)][string]$DevStateBucket,
    [Parameter(Mandatory)][string]$DevLockTable,
    [Parameter(Mandatory)][string]$DevSchedulerName,
    [Parameter(Mandatory)][string]$DevStateMachineArn,
    [Parameter(Mandatory)][string]$DevDbGuardParameter,
    [ValidateSet('ValidateInfrastructure', 'Success', 'Overlap', 'LockExpiry', 'Heartbeat', 'TransientRetry', 'Timeout', 'SpotInterruption', 'CapacityFallback', 'All')]
    [string]$Scenario = 'ValidateInfrastructure',
    [string]$ExecutionInputJson
)

$ErrorActionPreference = 'Stop'
$env:AWS_PAGER = ''

function Invoke-AwsJson {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $raw = & aws @Arguments --region $ExpectedRegion --output json
    if ($LASTEXITCODE -ne 0) { throw "AWS CLI command failed without persisted credentials." }
    if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
    return ($raw | ConvertFrom-Json -Depth 100)
}

function Assert-Equal {
    param([string]$Name, $Actual, $Expected)
    if ($Actual -ne $Expected) { throw "$Name expected '$Expected' but got '$Actual'." }
}

function Assert-False {
    param([string]$Name, $Value)
    if ([string]$Value -notin @('false', 'False', 'FALSE', '0')) {
        throw "$Name must be false for the dev harness."
    }
}

function Assert-DevName {
    param([string]$Name, [string]$Value, [string]$LogicalPrefix)
    if (-not $Value.StartsWith($LogicalPrefix, [StringComparison]::Ordinal)) {
        throw "$Name must start with '$LogicalPrefix'."
    }
    if ($Value -match '(?i)(^|[-_/])prod(uction)?($|[-_/])') {
        throw "$Name must not identify production."
    }
}

function Assert-GetCallerIdentity {
    $identity = Invoke-AwsJson -Arguments @('sts', 'get-caller-identity')
    Assert-Equal -Name 'AWS account' -Actual ([string]$identity.Account) -Expected $ExpectedAccountId
}

function Assert-DevInfrastructure {
    Assert-GetCallerIdentity
    Assert-DevName -Name 'DevStateBucket' -Value $DevStateBucket -LogicalPrefix 'inform-crawler-state-dev'
    Assert-DevName -Name 'DevLockTable' -Value $DevLockTable -LogicalPrefix 'inform-crawler-runtime-lock-dev'
    Assert-DevName -Name 'DevSchedulerName' -Value $DevSchedulerName -LogicalPrefix 'inform-crawler-scheduler-dev'
    Assert-DevName -Name 'DevStateMachineArn' -Value $DevStateMachineArn -LogicalPrefix 'arn:'

    $guard = & aws ssm get-parameter --name $DevDbGuardParameter --with-decryption `
        --query 'Parameter.Value' --output text --region $ExpectedRegion
    if ($LASTEXITCODE -ne 0) { throw 'Unable to read the dev DB denial guard.' }
    Assert-False -Name 'PRODUCTION_DB_ACCESS_ALLOWED' -Value $guard

    $versioning = Invoke-AwsJson -Arguments @('s3api', 'get-bucket-versioning', '--bucket', $DevStateBucket)
    Assert-Equal -Name 'S3 versioning' -Actual $versioning.Status -Expected 'Enabled'

    $encryption = Invoke-AwsJson -Arguments @('s3api', 'get-bucket-encryption', '--bucket', $DevStateBucket)
    $algorithm = $encryption.ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault.SSEAlgorithm
    Assert-Equal -Name 'S3 encryption' -Actual $algorithm -Expected 'AES256'

    $publicBlock = Invoke-AwsJson -Arguments @('s3api', 'get-public-access-block', '--bucket', $DevStateBucket)
    foreach ($property in @('BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets')) {
        Assert-Equal -Name "S3 $property" -Actual $publicBlock.PublicAccessBlockConfiguration.$property -Expected $true
    }

    $lifecycle = Invoke-AwsJson -Arguments @('s3api', 'get-bucket-lifecycle-configuration', '--bucket', $DevStateBucket)
    $requiredRules = @('history-runs-90-days', 'success-logs-30-days', 'failure-artifacts-90-days', 'failure-queue-30-days')
    foreach ($rule in $requiredRules) {
        if ($rule -notin $lifecycle.Rules.ID) { throw "Missing lifecycle rule '$rule'." }
    }

    $table = Invoke-AwsJson -Arguments @('dynamodb', 'describe-table', '--table-name', $DevLockTable)
    Assert-Equal -Name 'DynamoDB key' -Actual $table.Table.KeySchema[0].AttributeName -Expected 'lock_key'

    $schedule = Invoke-AwsJson -Arguments @('scheduler', 'get-schedule', '--name', $DevSchedulerName)
    Assert-Equal -Name 'Dev schedule state' -Actual $schedule.State -Expected 'DISABLED'
    Assert-Equal -Name 'Schedule timezone' -Actual $schedule.ScheduleExpressionTimezone -Expected 'Asia/Seoul'

    $definition = Invoke-AwsJson -Arguments @('stepfunctions', 'describe-state-machine', '--state-machine-arn', $DevStateMachineArn)
    if ($definition.definition -notmatch 'price-capacity-optimized') { throw 'Spot allocation contract is absent.' }
    if ($definition.definition -notmatch '"Seconds":600' -or $definition.definition -notmatch '"Seconds":1800') {
        throw 'Retry delays do not match the approved 10/30-minute contract.'
    }
}

function Get-ExecutionInput {
    param([string]$Simulation = 'NONE')
    if ([string]::IsNullOrWhiteSpace($ExecutionInputJson)) {
        throw 'ExecutionInputJson is required for worker execution scenarios.'
    }
    $inputObject = $ExecutionInputJson | ConvertFrom-Json -Depth 100
    $inputObject.Simulation = $Simulation
    return ($inputObject | ConvertTo-Json -Depth 100 -Compress)
}

function Start-DevExecution {
    param([string]$Simulation = 'NONE')
    $name = "harness-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
    $inputJson = Get-ExecutionInput -Simulation $Simulation
    $started = Invoke-AwsJson -Arguments @('stepfunctions', 'start-execution', '--state-machine-arn', $DevStateMachineArn, '--name', $name, '--input', $inputJson)
    return $started.executionArn
}

function Wait-DevExecution {
    param([Parameter(Mandatory)][string]$ExecutionArn)
    do {
        Start-Sleep -Seconds 30
        $execution = Invoke-AwsJson -Arguments @('stepfunctions', 'describe-execution', '--execution-arn', $ExecutionArn)
    } while ($execution.status -in @('RUNNING'))
    return $execution
}

function Assert-ExecutionSucceeded {
    param([string]$Simulation = 'NONE')
    $execution = Wait-DevExecution -ExecutionArn (Start-DevExecution -Simulation $Simulation)
    Assert-Equal -Name "Execution ($Simulation)" -Actual $execution.status -Expected 'SUCCEEDED'
    return $execution
}

function Test-LeasePrimitive {
    param([switch]$Expire, [switch]$Heartbeat)
    $key = "harness#$([Guid]::NewGuid().ToString('N'))"
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $expires = if ($Expire) { $now - 1 } else { $now + 1200 }
    $item = @{lock_key=@{S=$key}; owner_run_id=@{S='harness'}; acquired_at=@{N="$now"}; heartbeat_at=@{N="$now"}; lease_expires_at=@{N="$expires"}; generation=@{N='1'}} | ConvertTo-Json -Compress
    & aws dynamodb put-item --table-name $DevLockTable --item $item --region $ExpectedRegion | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Unable to write isolated harness lease.' }
    try {
        if ($Heartbeat) {
            $later = $now + 300
            $newExpiry = $later + 1200
            $values = @{':owner'=@{S='harness'};':generation'=@{N='1'};':heartbeat'=@{N="$later"};':expires'=@{N="$newExpiry"}} | ConvertTo-Json -Compress
            & aws dynamodb update-item --table-name $DevLockTable --key (@{lock_key=@{S=$key}} | ConvertTo-Json -Compress) `
                --condition-expression 'owner_run_id=:owner AND generation=:generation' `
                --update-expression 'SET heartbeat_at=:heartbeat, lease_expires_at=:expires' `
                --expression-attribute-values $values --region $ExpectedRegion | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'Heartbeat conditional update failed.' }
        }
        if ($Expire -and $expires -ge [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) {
            throw 'Isolated lease did not represent an expired takeover candidate.'
        }
    }
    finally {
        & aws dynamodb delete-item --table-name $DevLockTable --key (@{lock_key=@{S=$key}} | ConvertTo-Json -Compress) --region $ExpectedRegion | Out-Null
    }
}

function Assert-CapacityFallbackInput {
    $inputObject = (Get-ExecutionInput | ConvertFrom-Json -Depth 100)
    $subnets = @($inputObject.Overrides | ForEach-Object { $_.SubnetId } | Sort-Object -Unique)
    $types = @($inputObject.Overrides | ForEach-Object { $_.InstanceType } | Sort-Object -Unique)
    if ($subnets.Count -lt 2 -or $types.Count -lt 2) {
        throw 'Capacity fallback requires at least two subnets and two instance types.'
    }
}

function Assert-ExecutionFailed {
    param([string]$Simulation)
    $execution = Wait-DevExecution -ExecutionArn (Start-DevExecution -Simulation $Simulation)
    Assert-Equal -Name "Execution ($Simulation)" -Actual $execution.status -Expected 'FAILED'
}

Assert-DevInfrastructure

switch ($Scenario) {
    'ValidateInfrastructure' { break }
    'Success' { Assert-ExecutionSucceeded | Out-Null }
    'Overlap' {
        $firstArn = Start-DevExecution
        $secondArn = Start-DevExecution
        $first = Wait-DevExecution -ExecutionArn $firstArn
        $second = Wait-DevExecution -ExecutionArn $secondArn
        Assert-Equal -Name 'First overlap execution' -Actual $first.status -Expected 'SUCCEEDED'
        Assert-Equal -Name 'Second overlap execution' -Actual $second.status -Expected 'SUCCEEDED'
        if (($first.output + $second.output) -notmatch 'SKIPPED_OVERLAP') {
            throw 'Controlled overlap did not produce SKIPPED_OVERLAP.'
        }
    }
    'LockExpiry' { Test-LeasePrimitive -Expire }
    'Heartbeat' { Test-LeasePrimitive -Heartbeat }
    'TransientRetry' { Assert-ExecutionSucceeded -Simulation 'S3_TRANSIENT' | Out-Null }
    'Timeout' { Assert-ExecutionFailed -Simulation 'TIMEOUT' }
    'SpotInterruption' { Assert-ExecutionSucceeded -Simulation 'SPOT_INTERRUPTION' | Out-Null }
    'CapacityFallback' { Assert-CapacityFallbackInput }
    'All' {
        Assert-CapacityFallbackInput
        Test-LeasePrimitive -Expire
        Test-LeasePrimitive -Heartbeat
        Assert-ExecutionSucceeded | Out-Null
        Assert-ExecutionSucceeded -Simulation 'S3_TRANSIENT' | Out-Null
        Assert-ExecutionSucceeded -Simulation 'SPOT_INTERRUPTION' | Out-Null
        Assert-ExecutionFailed -Simulation 'TIMEOUT'
    }
}

Write-Host "Dev harness scenario '$Scenario' completed."

Assert-DevInfrastructure

$scenarios = if ($Scenario -eq 'All') {
    @('Success', 'Overlap', 'LockExpiry', 'Heartbeat', 'TransientRetry', 'Timeout', 'SpotInterruption', 'CapacityFallback')
} elseif ($Scenario -eq 'ValidateInfrastructure') { @() } else { @($Scenario) }

foreach ($selected in $scenarios) {
    switch ($selected) {
        'Success' { Assert-ExecutionSucceeded | Out-Null }
        'Overlap' {
            $first = Start-DevExecution
            $second = Start-DevExecution
            $results = @((Wait-DevExecution $first), (Wait-DevExecution $second))
            if (($results.output -join '') -notmatch 'SKIPPED_OVERLAP') { throw 'No overlap execution reported SKIPPED_OVERLAP.' }
        }
        'LockExpiry' { Test-LeasePrimitive -Expire }
        'Heartbeat' { Test-LeasePrimitive -Heartbeat }
        'TransientRetry' { Assert-ExecutionSucceeded -Simulation 'S3_TRANSIENT' | Out-Null }
        'Timeout' { Assert-ExecutionSucceeded -Simulation 'TIMEOUT' | Out-Null }
        'SpotInterruption' { Assert-ExecutionSucceeded -Simulation 'SPOT_INTERRUPTION' | Out-Null }
        'CapacityFallback' {
            $inputObject = (Get-ExecutionInput | ConvertFrom-Json -Depth 100)
            $subnets = @($inputObject.Overrides.SubnetId | Sort-Object -Unique)
            $types = @($inputObject.Overrides.InstanceType | Sort-Object -Unique)
            if ($subnets.Count -lt 2 -or $types.Count -lt 2) { throw 'Candidate pool fallback requires >=2 subnets and >=2 instance types.' }
        }
    }
}

Write-Output "Dev harness scenario '$Scenario' completed without production access."
