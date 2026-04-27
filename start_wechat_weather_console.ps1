$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Port = 8766
$Url = "http://127.0.0.1:$Port/"
$Python = "python"
$Config = Join-Path $Root "wechat_weather_config.example.json"
$Stdout = Join-Path $Root "wechat_weather_server.log"
$Stderr = Join-Path $Root "wechat_weather_server.err.log"

function Test-PortOpen {
    param([string]$HostName, [int]$PortNumber)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($HostName, $PortNumber, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(800, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

if (-not (Test-PortOpen -HostName "127.0.0.1" -PortNumber $Port)) {
    Start-Process `
        -FilePath $Python `
        -ArgumentList @(
            "-m", "wechat_weather.cli",
            "serve",
            "--config", $Config,
            "--window-handle", "199668",
            "--port", "$Port"
        ) `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $Stdout `
        -RedirectStandardError $Stderr

    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-PortOpen -HostName "127.0.0.1" -PortNumber $Port) {
            break
        }
    }
}

Start-Process $Url
