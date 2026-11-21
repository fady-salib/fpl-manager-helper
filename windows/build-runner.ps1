param(
    [Parameter(Mandatory=$true)][string]$WebViewSdk,
    [string]$EnginePath,
    [string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
if (!$EnginePath) { $EnginePath = Join-Path $project 'rust/target/release/fpl-manager.exe' }
if (!$OutputPath) { $OutputPath = Join-Path $project 'FPL Manager.exe' }
$WebViewSdk = (Resolve-Path -LiteralPath $WebViewSdk).Path
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$core = Join-Path $WebViewSdk 'lib/net462/Microsoft.Web.WebView2.Core.dll'
$winforms = Join-Path $WebViewSdk 'lib/net462/Microsoft.Web.WebView2.WinForms.dll'
$loader = Join-Path $WebViewSdk 'runtimes/win-x64/native/WebView2Loader.dll'
$installer = Join-Path $WebViewSdk 'MicrosoftEdgeWebview2Setup.exe'
$database = Join-Path $project 'data/fpl.sqlite'
$assets = [ordered]@{
    'fpl-manager.exe'                   = $EnginePath
    'Microsoft.Web.WebView2.Core.dll'    = $core
    'Microsoft.Web.WebView2.WinForms.dll'= $winforms
    'WebView2Loader.dll'                 = $loader
    'fpl.sqlite'                        = $database
    'native-model.json'                  = Join-Path $project 'models/native-model.json'
    'MicrosoftEdgeWebview2Setup.exe'      = $installer
    'FPL-Manager-License.txt'            = Join-Path $project 'LICENSE'
    'WebView2-License.txt'               = Join-Path $WebViewSdk 'LICENSE.txt'
    'WebView2-Notices.txt'               = Join-Path $WebViewSdk 'NOTICE.txt' 
}
# Package public snapshots only. A workspace's account registry is never a release input.
$check = @"
import re, sqlite3, sys
from pathlib import Path
with sqlite3.connect(Path(sys.argv[1]).resolve().as_uri() + '?mode=ro', uri=True) as db:
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {'snapshots'}, 'Use a public seed database containing only snapshots'
    assert all(re.fullmatch(r'(bootstrap-static/|fixtures/|element-summary/[0-9]+/)', row[0])
               for row in db.execute('SELECT DISTINCT endpoint FROM snapshots')), 'Non-public data in the seed database'
"@
$check | python - $database
if ($LASTEXITCODE -ne 0) { throw 'Public database validation failed.' }

$assetDir = Join-Path $project 'rust/target/runner-assets'
New-Item -ItemType Directory -Path $assetDir -Force | Out-Null
$arguments = @(
    '/nologo', '/optimize+', '/target:winexe', '/platform:x64', '/codepage:65001',
    "/win32icon:$(Join-Path $PSScriptRoot 'app.ico')",
    "/out:$OutputPath", '/reference:System.Net.Http.dll', '/reference:System.Web.Extensions.dll',
    '/reference:System.IO.Compression.dll', "/reference:$core", "/reference:$winforms",
    "/resource:$(Join-Path $project 'rust/web/index.html'),index.html",
    "/resource:$(Join-Path $project 'rust/web/app.css'),app.css",
    "/resource:$(Join-Path $project 'rust/web/app.js'),app.js",
    "/resource:$(Join-Path $PSScriptRoot 'import-fpl.js'),import-fpl.js",
    "/resource:$(Join-Path $PSScriptRoot 'review-transfers.js'),review-transfers.js"
)
foreach ($entry in $assets.GetEnumerator()) {
    $compressed = Join-Path $assetDir ($entry.Key + '.gz')
    $inputStream = [IO.File]::OpenRead($entry.Value)
    try {
        $outputStream = [IO.File]::Create($compressed)
        try {
            $gzip = [IO.Compression.GZipStream]::new($outputStream, [IO.Compression.CompressionLevel]::Optimal, $true)
            try { $inputStream.CopyTo($gzip) } finally { $gzip.Dispose() }
        } finally { $outputStream.Dispose() }
    } finally { $inputStream.Dispose() }
    $arguments += "/resource:$compressed,$($entry.Key).gz"
}
& $compiler @arguments (Join-Path $PSScriptRoot 'Runner.cs')
if ($LASTEXITCODE -ne 0) { throw "Windows runner compiler exited with $LASTEXITCODE." }
Get-Item -LiteralPath $OutputPath
