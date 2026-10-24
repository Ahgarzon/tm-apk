$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'sql_context_policy.ps1')
$valid = @{actions='true';repository='Ahgarzon/tm-apk';public='true';actorId='114458437';sha=('a'*40);expectedSha=('a'*40);nonce=('b'*32)}
Assert-TmSqlRequest $valid
$count = 1
foreach ($case in @(
    @('actions','false'), @('repository','Ahgarzon/tourmaps-backend'),
    @('public','false'), @('actorId','1'), @('sha',('c'*40)),
    @('expectedSha','main'), @('nonce','../escape'), @('nonce',('B'*32))
)) {
    $bad = $valid.Clone(); $bad[$case[0]] = $case[1]; $rejected = $false
    try { Assert-TmSqlRequest $bad } catch { $rejected = $true }
    if (-not $rejected) { throw 'Request accepted outside reviewed boundary' }; $count++
}
Assert-TmSqlIdentifier ('TmSql_' + ('b'*16)) $valid.nonce instance
foreach ($n in 0..3) { Assert-TmSqlIdentifier ('TmSql_' + ('b'*16) + '_c' + $n) $valid.nonce database; $count++ }
foreach ($target in @('master','tourmaps','TourMaps_restore_example',('TmSql_' + ('c'*16) + '_c0'))) {
    $rejected = $false
    try { Assert-TmSqlIdentifier $target $valid.nonce database } catch { $rejected = $true }
    if (-not $rejected) { throw 'An unowned database was accepted' }; $count++
}
$version=Select-TmSqlVersion @('Microsoft SQL Server 2019 (15.0.4382.1)')
if($version.request -cne '15.0' -or $version.installed -cne '15.0.4382.1') {throw 'CLI version not parsed'};$count++
$version=Select-TmSqlVersion @('Microsoft SQL Server 2022 (16.0.1000.6)','Microsoft SQL Server 2019 (15.0.4382.1)')
if($version.request -cne '15.0') {throw 'Installed major preference changed'};$count++
$rejected=$false;try {Select-TmSqlVersion @('SQL Server (17.0.1.1)')} catch {$rejected=$true}
if(-not $rejected) {throw 'Unreviewed major accepted'};$count++
foreach ($file in @('sql_context_policy.ps1','sql_context_probe.ps1','test_sql_context_policy.ps1')) {
    $tokens=$null; $parseErrors=$null
    [void][Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $file),[ref]$tokens,[ref]$parseErrors)
    if ($parseErrors.Count) { throw 'PowerShell syntax invalid' }
}
Write-Output ('SQL_CONTEXT_POLICY ' + (@{passed=$count;sqlStarted=$false}|ConvertTo-Json -Compress))
