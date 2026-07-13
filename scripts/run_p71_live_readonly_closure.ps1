[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CredentialTarget,

    [Parameter(Mandatory = $true)]
    [string]$CredentialReferenceId,

    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,

    [ValidateRange(30, 120)]
    [int]$TimeoutSeconds = 35
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-PythonStep {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )
    Write-Host "[P71] $Label"
    $output = & python @Arguments 2>&1
    $code = $LASTEXITCODE
    $output | ForEach-Object { Write-Host $_ }
    return [int]$code
}

$utc = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$operatorSessionId = "p71_operator_session_${utc}_$([Guid]::NewGuid().ToString('N'))"
$sessionDir = Join-Path $ProjectRoot "storage\p71\live_sessions\$operatorSessionId"
New-Item -ItemType Directory -Force -Path $sessionDir | Out-Null

$publicEvidence = Join-Path $sessionDir "public_evidence.json"
$privateReceipt = Join-Path $sessionDir "private_receipt.json"
$closureCopy = Join-Path $sessionDir "closure_report.json"

Push-Location $ProjectRoot
try {
    $publicExit = Invoke-PythonStep -Label "Public REST/WebSocket live evidence" -Arguments @(
        "scripts/run_p71_extended_public_probe.py",
        "--network-enabled",
        "--timeout-seconds", "$TimeoutSeconds",
        "--output", $publicEvidence
    )

    $privateExit = Invoke-PythonStep -Label "External private REST/account-WebSocket live evidence" -Arguments @(
        "-m", "external_runtime_packages.extended_read_only_probe.run_windows_probe",
        "--credential-target", $CredentialTarget,
        "--credential-reference-id", $CredentialReferenceId,
        "--network-enabled",
        "--timeout-seconds", "$TimeoutSeconds",
        "--output", $privateReceipt
    )

    if (-not (Test-Path $publicEvidence)) {
        throw "Public evidence file was not created: $publicEvidence"
    }
    if (-not (Test-Path $privateReceipt)) {
        throw "Private receipt file was not created: $privateReceipt"
    }

    $closureExit = Invoke-PythonStep -Label "Closure validation, anti-replay consumption, and redacted attestation" -Arguments @(
        "scripts/build_p71_extended_readonly_closure.py",
        "--public-evidence", $publicEvidence,
        "--private-receipt", $privateReceipt,
        "--project-root", $ProjectRoot,
        "--operator-session-id", $operatorSessionId,
        "--output", $closureCopy
    )

    Write-Host "[P71] operator_session_id=$operatorSessionId"
    Write-Host "[P71] public_probe_exit=$publicExit"
    Write-Host "[P71] private_probe_exit=$privateExit"
    Write-Host "[P71] closure_exit=$closureExit"
    Write-Host "[P71] session_dir=$sessionDir"
    Write-Host "[P71] No API-key value, Stark private key, signature, order, or cancel request was accepted by this runner."

    if ($closureExit -ne 0) {
        exit $closureExit
    }
    exit 0
}
finally {
    Pop-Location
}
