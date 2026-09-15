[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^\d{12}$')][string]$ExpectedAccountId,
    [Parameter(Mandatory)][string]$ExpectedRegion,
    [Parameter(Mandatory)][string]$DevStateBucket,
    [Parameter(Mandatory)][string]$DevLockTable,
    [Parameter(Mandatory)][string]$DevSchedulerName,
    [Parameter(Mandatory)][string]$DevStateMachineArn,
    [Parameter(Mandatory)][string]$DevDbGuardParameter,
    [Parameter(Mandatory)][long]$CredentialExpiresAtEpoch,
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9]{6,32}$')][string]$HarnessRunId,
    # Keep each AWS-mutating scenario explicit so the coordinator can approve one scope per invocation.
    [ValidateSet('ValidateInfrastructure', 'Success', 'Overlap', 'LockExpiry', 'Heartbeat', 'TransientRetry', 'Timeout', 'SpotInterruption', 'CapacityFallback')]
    [string]$Scenario = 'ValidateInfrastructure',
    [string]$ExecutionInputJson
)

$ErrorActionPreference = 'Stop'
$env:AWS_PAGER = ''
$LeaseLockKey = 'daily-crawler'
$AcquireLeaseCondition = 'attribute_not_exists(lock_key) OR lease_expires_at < :now'
$HarnessLeasePrecondition = 'attribute_not_exists(lock_key) OR (owner_run_id=:empty AND lease_expires_at < :now)'
$OwnedLeaseCondition = 'owner_run_id=:owner AND generation=:generation'
$AcquireLeaseUpdate = 'SET owner_run_id=:owner, acquired_at=:now, heartbeat_at=:now, lease_expires_at=:expires, generation=if_not_exists(generation,:zero)+:one'
$CredentialCleanupBufferSeconds = 600
$script:ActiveExecutionArns = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)

function Invoke-AwsJson {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $raw = & aws @Arguments --region $ExpectedRegion --output json
    if ($LASTEXITCODE -ne 0) { throw "AWS CLI command failed without persisted credentials." }
    if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
    return ($raw | ConvertFrom-Json -Depth 100)
}

function Invoke-ReadOnlyAwsJsonWithRetry {
    param(
        [Parameter(Mandatory)][string[]]$Arguments,
        [ValidateRange(1, 5)][int]$MaxAttempts = 3,
        [ValidateRange(0, 30)][int]$RetryDelaySeconds = 5
    )
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            return Invoke-AwsJson -Arguments $Arguments
        }
        catch {
            if ($attempt -lt $MaxAttempts) {
                Start-Sleep -Seconds $RetryDelaySeconds
                continue
            }
            throw "AWS CLI read-only polling command failed after $MaxAttempts attempts without persisted credentials."
        }
    }
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
    Write-Output 'HARNESS_STAGE name=DevIdentity'
    Assert-GetCallerIdentity

    Write-Output 'HARNESS_STAGE name=DevNaming'
    Assert-DevName -Name 'DevStateBucket' -Value $DevStateBucket -LogicalPrefix 'inform-crawler-state-dev'
    Assert-DevName -Name 'DevLockTable' -Value $DevLockTable -LogicalPrefix 'inform-crawler-runtime-lock-dev'
    Assert-DevName -Name 'DevSchedulerName' -Value $DevSchedulerName -LogicalPrefix 'inform-crawler-scheduler-dev'
    Assert-DevName -Name 'DevStateMachineArn' -Value $DevStateMachineArn -LogicalPrefix "arn:aws:states:$ExpectedRegion`:$ExpectedAccountId`:stateMachine:inform-crawler-orchestration-dev"
    Assert-Equal -Name 'DevDbGuardParameter' -Actual $DevDbGuardParameter -Expected '/inform/crawler/dev/PRODUCTION_DB_ACCESS_ALLOWED'

    Write-Output 'HARNESS_STAGE name=DevDbGuard'
    $guard = & aws ssm get-parameter --name $DevDbGuardParameter --with-decryption `
        --query 'Parameter.Value' --output text --region $ExpectedRegion
    if ($LASTEXITCODE -ne 0) { throw 'Unable to read the dev DB denial guard.' }
    Assert-False -Name 'PRODUCTION_DB_ACCESS_ALLOWED' -Value $guard

    Write-Output 'HARNESS_STAGE name=DevStateBucket'
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

    Write-Output 'HARNESS_STAGE name=DevLockTable'
    $table = Invoke-AwsJson -Arguments @('dynamodb', 'describe-table', '--table-name', $DevLockTable)
    Assert-Equal -Name 'DynamoDB key' -Actual $table.Table.KeySchema[0].AttributeName -Expected 'lock_key'

    Write-Output 'HARNESS_STAGE name=DevScheduler'
    $schedule = Invoke-AwsJson -Arguments @('scheduler', 'get-schedule', '--name', $DevSchedulerName)
    Assert-Equal -Name 'Dev schedule state' -Actual $schedule.State -Expected 'DISABLED'
    Assert-Equal -Name 'Schedule timezone' -Actual $schedule.ScheduleExpressionTimezone -Expected 'Asia/Seoul'

    Write-Output 'HARNESS_STAGE name=DevStateMachine'
    $definition = Invoke-AwsJson -Arguments @('stepfunctions', 'describe-state-machine', '--state-machine-arn', $DevStateMachineArn)
    if ($definition.definition -notmatch 'price-capacity-optimized') { throw 'Spot allocation contract is absent.' }
    if ($definition.definition -notmatch '"Seconds"\s*:\s*600' -or $definition.definition -notmatch '"Seconds"\s*:\s*1800') {
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
    $name = "harness-$HarnessRunId-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
    $inputJson = Get-ExecutionInput -Simulation $Simulation
    $started = Invoke-AwsJson -Arguments @('stepfunctions', 'start-execution', '--state-machine-arn', $DevStateMachineArn, '--name', $name, '--input', $inputJson)
    $executionArn = [string]$started.executionArn
    if ([string]::IsNullOrWhiteSpace($executionArn)) {
        throw 'Started dev execution did not return an execution ARN.'
    }
    $null = $script:ActiveExecutionArns.Add($executionArn)
    return $executionArn
}

function Stop-ActiveDevExecutions {
    $failed = 0
    foreach ($executionArn in @($script:ActiveExecutionArns)) {
        try {
            Invoke-AwsJson -Arguments @(
                'stepfunctions', 'stop-execution',
                '--execution-arn', $executionArn,
                '--error', 'DevHarnessCleanup',
                '--cause', 'Stopped by the bounded dev harness cleanup path.',
                '--cli-connect-timeout', '5',
                '--cli-read-timeout', '10'
            ) | Out-Null
            $null = $script:ActiveExecutionArns.Remove($executionArn)
        }
        catch {
            $failed++
        }
    }
    if ($failed -gt 0) {
        throw "Unable to stop $failed started dev execution(s)."
    }
}

function Stop-DevExecutionBeforeCredentialExpiry {
    param([Parameter(Mandatory)][string]$ExecutionArn)
    Write-Output 'HARNESS_STAGE name=CredentialSafetyStop'
    Stop-ActiveDevExecutions
    throw 'Dev harness stopped execution before temporary role credentials expire.'
}

function Wait-DevExecution {
    param([Parameter(Mandatory)][string]$ExecutionArn)
    $credentialSafetyDeadline = $CredentialExpiresAtEpoch - $CredentialCleanupBufferSeconds
    while ($true) {
        $remainingSeconds = $credentialSafetyDeadline - [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        if ($remainingSeconds -le 0) {
            Stop-DevExecutionBeforeCredentialExpiry -ExecutionArn $ExecutionArn
        }
        try {
            $execution = Invoke-ReadOnlyAwsJsonWithRetry -Arguments @('stepfunctions', 'describe-execution', '--execution-arn', $ExecutionArn)
        }
        catch {
            Stop-ActiveDevExecutions
            throw
        }
        if ($execution.status -notin @('RUNNING')) {
            $null = $script:ActiveExecutionArns.Remove($ExecutionArn)
            return $execution
        }
        Start-Sleep -Seconds ([Math]::Min(30, [Math]::Max(1, $remainingSeconds)))
    }
}

function Assert-ExecutionSucceeded {
    param([string]$Simulation = 'NONE')
    $execution = Wait-DevExecution -ExecutionArn (Start-DevExecution -Simulation $Simulation)
    Assert-Equal -Name "Execution ($Simulation)" -Actual $execution.status -Expected 'SUCCEEDED'
    return $execution
}

function Get-HarnessLeaseKeyJson {
    return (@{lock_key=@{S=$LeaseLockKey}} | ConvertTo-Json -Compress)
}

function Assert-LiveLeasePathContract {
    if ([string]::IsNullOrWhiteSpace($ExecutionInputJson)) {
        throw 'ExecutionInputJson is required to verify the live lease path.'
    }

    $inputObject = $ExecutionInputJson | ConvertFrom-Json -Depth 100
    $workerDocumentName = [string]$inputObject.WorkerDocumentName
    if ([string]::IsNullOrWhiteSpace($workerDocumentName)) {
        throw 'ExecutionInputJson does not identify the worker document.'
    }
    Assert-DevName -Name 'WorkerDocumentName' -Value $workerDocumentName -LogicalPrefix 'inform-crawler-worker-dev'

    $stateMachine = Invoke-AwsJson -Arguments @('stepfunctions', 'describe-state-machine', '--state-machine-arn', $DevStateMachineArn)
    $definition = $stateMachine.definition | ConvertFrom-Json -Depth 100
    $sendWorkerCommand = $definition.States.SendWorkerCommand
    if ($null -eq $sendWorkerCommand) { throw "State machine is missing 'SendWorkerCommand'." }
    Assert-Equal -Name 'Worker command integration' -Actual ([string]$sendWorkerCommand.Resource) -Expected 'arn:aws:states:::aws-sdk:ssm:sendCommand'
    Assert-Equal -Name 'Worker document binding' -Actual ([string]$sendWorkerCommand.Parameters.'DocumentName.$') -Expected '$.WorkerDocumentName'

    $document = Invoke-AwsJson -Arguments @('ssm', 'get-document', '--name', $workerDocumentName, '--document-version', '$LATEST')
    $documentContent = $document.Content | ConvertFrom-Json -Depth 100
    $workerCommand = [string]::Join("`n", [string[]]$documentContent.mainSteps[0].inputs.runCommand)
    foreach ($fragment in @(
        "readonly LOCK_KEY='$LeaseLockKey'",
        $AcquireLeaseCondition,
        $OwnedLeaseCondition,
        'generation=if_not_exists(generation,:zero)+:one'
    )) {
        if (-not $workerCommand.Contains($fragment, [StringComparison]::Ordinal)) {
            throw "Live worker document is missing the lease contract fragment '$fragment'."
        }
    }
}

function Assert-HarnessLeasePrecondition {
    param(
        [Parameter(Mandatory)][string]$Owner,
        [Parameter(Mandatory)][long]$Now,
        [Parameter(Mandatory)][long]$Expires
    )
    return Invoke-HarnessLeaseAcquire -Owner $Owner -Now $Now -Expires $Expires -RequireReleased
}

function New-HarnessLeaseValuesJson {
    param(
        [Parameter(Mandatory)][string]$Owner,
        [Parameter(Mandatory)][long]$Now,
        [Parameter(Mandatory)][long]$Expires,
        [switch]$IncludeEmpty
    )
    $values = @{
        ':owner'=@{S=$Owner}
        ':now'=@{N="$Now"}
        ':expires'=@{N="$Expires"}
        ':zero'=@{N='0'}
        ':one'=@{N='1'}
    }
    if ($IncludeEmpty) { $values[':empty'] = @{S=''} }
    return ($values | ConvertTo-Json -Compress)
}

function Invoke-HarnessLeaseAcquire {
    param(
        [Parameter(Mandatory)][string]$Owner,
        [Parameter(Mandatory)][long]$Now,
        [Parameter(Mandatory)][long]$Expires,
        [switch]$RequireReleased
    )

    $condition = if ($RequireReleased) { $HarnessLeasePrecondition } else { $AcquireLeaseCondition }
    $values = New-HarnessLeaseValuesJson -Owner $Owner -Now $Now -Expires $Expires -IncludeEmpty:$RequireReleased
    $response = Invoke-AwsJson -Arguments @(
        'dynamodb', 'update-item', '--table-name', $DevLockTable,
        '--key', (Get-HarnessLeaseKeyJson),
        '--condition-expression', $condition,
        '--update-expression', $AcquireLeaseUpdate,
        '--expression-attribute-values', $values,
        '--return-values', 'ALL_NEW'
    )
    $generationText = [string]$response.Attributes.generation.N
    [long]$generation = 0
    if (-not [long]::TryParse($generationText, [ref]$generation) -or $generation -lt 1) {
        throw 'Lease acquisition returned an invalid generation.'
    }
    Assert-Equal -Name 'Lease acquisition owner' -Actual ([string]$response.Attributes.owner_run_id.S) -Expected $Owner
    return $generation
}

function Set-HarnessLeaseWindow {
    param(
        [Parameter(Mandatory)][string]$Owner,
        [Parameter(Mandatory)][long]$Generation,
        [Parameter(Mandatory)][long]$Heartbeat,
        [Parameter(Mandatory)][long]$Expires
    )

    $values = @{
        ':owner'=@{S=$Owner}
        ':generation'=@{N="$Generation"}
        ':heartbeat'=@{N="$Heartbeat"}
        ':expires'=@{N="$Expires"}
    } | ConvertTo-Json -Compress
    Invoke-AwsJson -Arguments @(
        'dynamodb', 'update-item', '--table-name', $DevLockTable,
        '--key', (Get-HarnessLeaseKeyJson),
        '--condition-expression', $OwnedLeaseCondition,
        '--update-expression', 'SET heartbeat_at=:heartbeat, lease_expires_at=:expires',
        '--expression-attribute-values', $values
    ) | Out-Null
}

function Invoke-HarnessLeaseHeartbeat {
    param(
        [Parameter(Mandatory)][string]$Owner,
        [Parameter(Mandatory)][long]$Generation,
        [Parameter(Mandatory)][long]$Heartbeat,
        [Parameter(Mandatory)][long]$Expires
    )
    Set-HarnessLeaseWindow -Owner $Owner -Generation $Generation -Heartbeat $Heartbeat -Expires $Expires
}

function Assert-HarnessLeaseState {
    param(
        [Parameter(Mandatory)][string]$Owner,
        [Parameter(Mandatory)][long]$Generation,
        [Parameter(Mandatory)][long]$Heartbeat,
        [Parameter(Mandatory)][long]$Expires
    )

    $values = @{
        ':owner'=@{S=$Owner}
        ':generation'=@{N="$Generation"}
        ':heartbeat'=@{N="$Heartbeat"}
        ':expires'=@{N="$Expires"}
    } | ConvertTo-Json -Compress
    Invoke-AwsJson -Arguments @(
        'dynamodb', 'update-item', '--table-name', $DevLockTable,
        '--key', (Get-HarnessLeaseKeyJson),
        '--condition-expression', 'owner_run_id=:owner AND generation=:generation AND heartbeat_at=:heartbeat AND lease_expires_at=:expires',
        '--update-expression', 'SET owner_run_id=:owner',
        '--expression-attribute-values', $values
    ) | Out-Null
}

function Clear-HarnessLease {
    param(
        [Parameter(Mandatory)][string]$Owner,
        [Parameter(Mandatory)][long]$Generation
    )
    if (-not $Owner.StartsWith('harness-lease-', [StringComparison]::Ordinal)) {
        throw 'Refusing to clean up a lease that is not harness-owned.'
    }

    $values = @{
        ':owner'=@{S=$Owner}
        ':generation'=@{N="$Generation"}
        ':zero'=@{N='0'}
        ':empty'=@{S=''}
    } | ConvertTo-Json -Compress
    Invoke-AwsJson -Arguments @(
        'dynamodb', 'update-item', '--table-name', $DevLockTable,
        '--key', (Get-HarnessLeaseKeyJson),
        '--condition-expression', $OwnedLeaseCondition,
        '--update-expression', 'SET owner_run_id=:empty, heartbeat_at=:zero, lease_expires_at=:zero',
        '--expression-attribute-values', $values
    ) | Out-Null
}

function Assert-HarnessLeaseAcquireRejected {
    param(
        [Parameter(Mandatory)][string]$Owner,
        [Parameter(Mandatory)][long]$Now,
        [Parameter(Mandatory)][long]$Expires
    )

    $values = New-HarnessLeaseValuesJson -Owner $Owner -Now $Now -Expires $Expires
    $arguments = @(
        'dynamodb', 'update-item', '--table-name', $DevLockTable,
        '--key', (Get-HarnessLeaseKeyJson),
        '--condition-expression', $AcquireLeaseCondition,
        '--update-expression', $AcquireLeaseUpdate,
        '--expression-attribute-values', $values,
        '--return-values', 'ALL_NEW',
        '--region', $ExpectedRegion, '--output', 'json'
    )
    $raw = & aws @arguments 2>&1
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq 0) {
        $unexpected = $raw | ConvertFrom-Json -Depth 100
        $unexpectedGeneration = [long]$unexpected.Attributes.generation.N
        Clear-HarnessLease -Owner $Owner -Generation $unexpectedGeneration
        throw 'An active daily-crawler lease unexpectedly allowed takeover.'
    }
    if (($raw | Out-String) -notmatch 'ConditionalCheckFailedException') {
        throw 'The active-lease rejection probe failed for a reason other than the lease condition.'
    }
}

function Test-LockExpiryLease {
    Write-Output 'HARNESS_STAGE name=LiveLeaseContract'
    Assert-LiveLeasePathContract
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $activeOwner = "harness-lease-active-$([Guid]::NewGuid().ToString('N'))"
    $takeoverOwner = "harness-lease-takeover-$([Guid]::NewGuid().ToString('N'))"
    $cleanupOwner = $null
    $cleanupGeneration = $null
    try {
        $activeExpiry = $now + 1200
        Write-Output 'HARNESS_STAGE name=LeasePrecondition'
        $activeGeneration = Assert-HarnessLeasePrecondition -Owner $activeOwner -Now $now -Expires $activeExpiry
        $cleanupOwner = $activeOwner
        $cleanupGeneration = $activeGeneration
        Assert-HarnessLeaseState -Owner $activeOwner -Generation $activeGeneration -Heartbeat $now -Expires $activeExpiry

        Write-Output 'HARNESS_STAGE name=ActiveLeaseRejection'
        Assert-HarnessLeaseAcquireRejected -Owner $takeoverOwner -Now ($now + 1) -Expires ($now + 1201)

        Write-Output 'HARNESS_STAGE name=ExpiredLeaseTakeover'
        $expiredAt = $now - 1
        Set-HarnessLeaseWindow -Owner $activeOwner -Generation $activeGeneration -Heartbeat $expiredAt -Expires $expiredAt
        $takeoverNow = $now + 2
        $takeoverExpiry = $takeoverNow + 1200
        $takeoverGeneration = Invoke-HarnessLeaseAcquire -Owner $takeoverOwner -Now $takeoverNow -Expires $takeoverExpiry
        $cleanupOwner = $takeoverOwner
        $cleanupGeneration = $takeoverGeneration
        Assert-Equal -Name 'Expired lease takeover generation' -Actual $takeoverGeneration -Expected ($activeGeneration + 1)
        Assert-HarnessLeaseState -Owner $takeoverOwner -Generation $takeoverGeneration -Heartbeat $takeoverNow -Expires $takeoverExpiry
    }
    finally {
        if ($null -ne $cleanupGeneration) {
            Clear-HarnessLease -Owner $cleanupOwner -Generation $cleanupGeneration
        }
    }
}

function Test-HeartbeatLease {
    Write-Output 'HARNESS_STAGE name=LiveLeaseContract'
    Assert-LiveLeasePathContract
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $owner = "harness-lease-heartbeat-$([Guid]::NewGuid().ToString('N'))"
    $takeoverOwner = "harness-lease-heartbeat-probe-$([Guid]::NewGuid().ToString('N'))"
    $generation = $null
    try {
        $originalExpiry = $now + 1200
        Write-Output 'HARNESS_STAGE name=LeasePrecondition'
        $generation = Assert-HarnessLeasePrecondition -Owner $owner -Now $now -Expires $originalExpiry
        $heartbeatAt = $now + 300
        $heartbeatExpiry = $heartbeatAt + 1200
        Write-Output 'HARNESS_STAGE name=HeartbeatExtension'
        Invoke-HarnessLeaseHeartbeat -Owner $owner -Generation $generation -Heartbeat $heartbeatAt -Expires $heartbeatExpiry
        Assert-HarnessLeaseState -Owner $owner -Generation $generation -Heartbeat $heartbeatAt -Expires $heartbeatExpiry

        # DynamoDB compares the supplied application time. Probe just past the original
        # deadline to prove that the heartbeat extension still rejects takeover.
        $probeNow = $originalExpiry + 1
        Write-Output 'HARNESS_STAGE name=ActiveLeaseRejection'
        Assert-HarnessLeaseAcquireRejected -Owner $takeoverOwner -Now $probeNow -Expires ($probeNow + 1200)
    }
    finally {
        if ($null -ne $generation) {
            Clear-HarnessLease -Owner $owner -Generation $generation
        }
    }
}

function Assert-CapacityFallbackDefinition {
    $stateMachine = Invoke-AwsJson -Arguments @('stepfunctions', 'describe-state-machine', '--state-machine-arn', $DevStateMachineArn)
    $definition = $stateMachine.definition | ConvertFrom-Json -Depth 100
    $overrides = @($definition.States.LaunchSpotWorker.Parameters.LaunchTemplateConfigs[0].Overrides)
    $subnets = @($overrides | ForEach-Object { $_.SubnetId } | Sort-Object -Unique)
    $types = @($overrides | ForEach-Object { $_.InstanceType } | Sort-Object -Unique)
    if ($subnets.Count -lt 2 -or $types.Count -lt 2) {
        throw 'Capacity fallback requires at least two subnets and two instance types.'
    }
}

function Assert-ExecutionFailed {
    param([string]$Simulation)
    $execution = Wait-DevExecution -ExecutionArn (Start-DevExecution -Simulation $Simulation)
    Assert-Equal -Name "Execution ($Simulation)" -Actual $execution.status -Expected 'FAILED'
}

Write-Output 'HARNESS_STAGE name=DevInfrastructure'
Assert-DevInfrastructure

try {
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
        'LockExpiry' { Test-LockExpiryLease }
        'Heartbeat' { Test-HeartbeatLease }
        'TransientRetry' { Assert-ExecutionSucceeded -Simulation 'S3_TRANSIENT' | Out-Null }
        'Timeout' { Assert-ExecutionFailed -Simulation 'TIMEOUT' }
        'SpotInterruption' { Assert-ExecutionSucceeded -Simulation 'SPOT_INTERRUPTION' | Out-Null }
        'CapacityFallback' { Assert-CapacityFallbackDefinition }
    }
}
finally {
    Stop-ActiveDevExecutions
}

Write-Output "Dev harness scenario '$Scenario' completed without production access."
