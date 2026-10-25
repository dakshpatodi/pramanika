# check_phase8_files.ps1
# Keep this script and phase8-files.txt OUTSIDE the repository (for example in Downloads) so they are not
# themselves reported. Then run:
#   powershell -ExecutionPolicy Bypass -File .\check_phase8_files.ps1 -RepoRoot C:\Users\jaine\OneDrive\Desktop\pramanika
# (without -RepoRoot it uses the current folder.)
# Read-only: it only runs "git status" and compares the result with phase8-files.txt.
# It tells you (1) which Phase 8 files are changed/added in your working tree,
# (2) which Phase 8 files are NOT (probably not applied yet), and
# (3) which changed files are NOT part of Phase 8 (unrelated work: do not commit them with it).
param([string]$RepoRoot = (Get-Location).Path)
$ErrorActionPreference = "Stop"

$listFile = Join-Path $PSScriptRoot "phase8-files.txt"
if (-not (Test-Path $listFile)) { throw "phase8-files.txt must sit next to this script." }

$expected = @{}
foreach ($line in Get-Content $listFile) {
    if (-not $line -or $line.StartsWith("#")) { continue }
    $parts = $line -split "`t"
    $expected[$parts[1].Trim()] = $parts[0].Trim()
}

$changed = @{}
foreach ($line in (git -C $RepoRoot status --porcelain -uall)) {
    if ($line.Length -lt 4) { continue }
    $code = $line.Substring(0, 2).Trim()
    $path = $line.Substring(3).Trim()
    if ($path -like "* -> *") { $path = ($path -split " -> ")[-1] }
    $path = $path.Trim('"')
    $changed[$path] = $code
}

$present = @(); $missing = @(); $unrelated = @(); $deleted = @()
foreach ($path in ($expected.Keys | Sort-Object)) {
    if ($changed.ContainsKey($path)) { $present += $path } else { $missing += $path }
}
foreach ($path in ($changed.Keys | Sort-Object)) {
    if (-not $expected.ContainsKey($path)) { $unrelated += ("{0,-3} {1}" -f $changed[$path], $path) }
    if ($changed[$path] -eq "D") { $deleted += $path }
}

Write-Host ""
Write-Host ("Phase 8 files changed or added in your working tree: {0} of {1}" -f $present.Count, $expected.Count)
Write-Host ""
Write-Host "Phase 8 files NOT changed (not applied yet, or already identical to git):"
if ($missing.Count -eq 0) { Write-Host "  (none)" } else { $missing | ForEach-Object { Write-Host "  $_" } }
Write-Host ""
Write-Host "Changed files that are NOT part of Phase 8 (unrelated; leave them out of the Phase 8 commit):"
if ($unrelated.Count -eq 0) { Write-Host "  (none)" } else { $unrelated | ForEach-Object { Write-Host "  $_" } }
Write-Host ""
Write-Host "Deleted files (Phase 8 deletes nothing):"
if ($deleted.Count -eq 0) { Write-Host "  (none)" } else { $deleted | ForEach-Object { Write-Host "  $_" } }
Write-Host ""
