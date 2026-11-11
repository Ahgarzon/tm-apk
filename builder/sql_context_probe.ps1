param([switch]$Worker, [string]$PlanPath)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.Data
. (Join-Path $PSScriptRoot 'sql_context_policy.ps1')
Assert-TmSqlRequest @{actions=$env:GITHUB_ACTIONS;repository=$env:GITHUB_REPOSITORY;public=$env:TM_PUBLIC;actorId=$env:GITHUB_ACTOR_ID;sha=$env:GITHUB_SHA;expectedSha=$env:TM_EXPECTED_SHA;nonce=$env:TM_NONCE}
$nonce=$env:TM_NONCE; $instance='TmSql_'+$nonce.Substring(0,16)
Assert-TmSqlIdentifier $instance $nonce instance
$root=Join-Path $env:RUNNER_TEMP ('TourMapsSqlContext\'+$nonce)
$expectedPlan=Join-Path $root 'intent.json'
function Free-MiB { return [int]((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1024) }
function Capacity([int]$Minimum) {
    if ((Free-MiB) -lt $Minimum -or (Get-Item -LiteralPath $env:RUNNER_TEMP).PSDrive.Free -lt 2304MB) { throw 'Resource guard' }
}
function Save-Json([string]$Name,[object]$Value) {
    $path=Join-Path $root $Name
    $stream=New-Object IO.FileStream($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try { $bytes=[Text.Encoding]::UTF8.GetBytes(($Value|ConvertTo-Json -Depth 12 -Compress)); $stream.Write($bytes,0,$bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}
function Open-OwnSql {
    $builder=New-Object Data.SqlClient.SqlConnectionStringBuilder
    $builder['Data Source']='(localdb)\'+$instance; $builder['Initial Catalog']='master'
    $builder['Integrated Security']=$true; $builder['Pooling']=$false; $builder['Connect Timeout']=8
    $builder['Application Name']='TourMaps synthetic context diagnostic'
    $connection=New-Object Data.SqlClient.SqlConnection $builder.ConnectionString
    $connection.Open(); return $connection
}
function Read-Sql($Connection,[string]$Sql) {
    $command=$Connection.CreateCommand(); $command.CommandTimeout=8; $command.CommandText=$Sql
    $table=New-Object Data.DataTable; $adapter=New-Object Data.SqlClient.SqlDataAdapter $command
    try { [void]$adapter.Fill($table); return ,$table } finally { $adapter.Dispose();$command.Dispose() }
}
function Exec-Sql($Connection,[string]$Sql) { [void](Read-Sql $Connection $Sql) }
function Sql-Codes($ErrorRecord) {
    $e=$ErrorRecord.Exception
    for($n=0;$n -lt 8 -and $null -ne $e;$n++) {
        if($e -is [Data.SqlClient.SqlException]) { return @{number=$e.Number;state=$e.State;class=$e.Class} }; $e=$e.InnerException
    }
    return @{failureType=$ErrorRecord.Exception.GetType().Name}
}
if ($Worker) {
    if ([IO.Path]::GetFullPath($PlanPath) -cne [IO.Path]::GetFullPath($expectedPlan)) { throw 'Unowned plan' }
    $plan=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8|ConvertFrom-Json
    if($plan.nonce -cne $nonce -or $plan.source -cne $env:GITHUB_SHA -or $plan.instance -cne $instance) { throw 'Plan mismatch' }
    $cases=@();$databases=@();$completed=$false;$cleaned=$false;$phase='setup';$failure=$null
    try {
        foreach($n in 0..3) {
            Capacity 2048
            $db=$instance+'_c'+$n; Assert-TmSqlIdentifier $db $nonce database
            $restricted=($n -ge 2);$connect=($n%2 -eq 1)
            $connection=Open-OwnSql
            try {
                if((Read-Sql $connection "SELECT COUNT(*) AS n FROM sys.databases WHERE name='$db';").Rows[0].n -ne 0) { throw 'Database already present' }
                $data=(Join-Path $root ($db+'.mdf')).Replace("'","''");$log=(Join-Path $root ($db+'.ldf')).Replace("'","''")
                $phase='create-synthetic-database';$databases+= $db
                Exec-Sql $connection "CREATE DATABASE [$db] ON (NAME=N'$db',FILENAME=N'$data',SIZE=8MB,MAXSIZE=32MB,FILEGROWTH=8MB) LOG ON (NAME=N'${db}_log',FILENAME=N'$log',SIZE=8MB,MAXSIZE=32MB,FILEGROWTH=8MB);"
                Exec-Sql $connection "USE [$db];SET LOCK_TIMEOUT 2000;SET XACT_ABORT ON;CREATE TABLE dbo.ContextProbe(Id int NOT NULL PRIMARY KEY);INSERT dbo.ContextProbe VALUES(1);CREATE USER [context_reader] WITHOUT LOGIN;GRANT SELECT ON OBJECT::dbo.ContextProbe TO [context_reader];"
                if($connect) { Exec-Sql $connection 'GRANT CONNECT TO [context_reader];' }
                if($restricted) { Exec-Sql $connection "ALTER DATABASE [$db] SET RESTRICTED_USER;" }
                $meta=(Read-Sql $connection "SELECT CONVERT(nvarchar(60),DATABASEPROPERTYEX(DB_NAME(),'UserAccess')) AS mode,(SELECT COUNT(*) FROM sys.database_permissions WHERE grantee_principal_id=DATABASE_PRINCIPAL_ID('context_reader') AND permission_name='CONNECT' AND state IN('G','W')) AS connectGrants;").Rows[0]
                $row=@{case=$n;mode=[string]$meta.mode;explicitConnectRequested=$connect;connectGrants=[int]$meta.connectGrants;contextReturned=$false;readAccepted=$false}
                $phase='execute-as-user';$row.phase=$phase
                try {
                    Exec-Sql $connection "EXECUTE AS USER='context_reader';"
                    $row.contextReturned=$true;$phase='select-as-reader';$row.phase=$phase
                    $read=(Read-Sql $connection "SELECT COUNT(*) AS n,IS_MEMBER('db_owner') AS ownerRole,HAS_PERMS_BY_NAME(DB_NAME(),'DATABASE','CONTROL') AS controlDb FROM dbo.ContextProbe WHERE Id=1;").Rows[0]
                    if($read.n -ne 1 -or $read.ownerRole -ne 0 -or $read.controlDb -ne 0) { throw 'Reader boundary invalid' }
                    $row.readAccepted=$true
                } catch { $row.error=Sql-Codes $_ }
                $cases+=$row
            } finally { $connection.Dispose() }
        }
        $completed=($cases.Count -eq 4)
    } catch { $failure=@{phase=$phase;error=(Sql-Codes $_)} }
    finally {
        $cleanup=Open-OwnSql
        try {
            foreach($db in $databases) { Assert-TmSqlIdentifier $db $nonce database;Exec-Sql $cleanup "IF DB_ID('$db') IS NOT NULL DROP DATABASE [$db];" }
            $remaining=0
            foreach($db in $databases) { $remaining += [int](Read-Sql $cleanup "SELECT COUNT(*) AS n FROM sys.databases WHERE name='$db';").Rows[0].n }
            $cleaned=($remaining -eq 0)
        } finally { $cleanup.Dispose() }
        Save-Json 'worker-result.json' @{cases=$cases;matrixCompleted=$completed;databaseCleanupVerified=$cleaned;failure=$failure;originalRowsRead=$false;originalRowsModified=$false;fullApplicationAccepted=$false;localRestoredCopyTested=$false}
    }
    if(-not $completed -or -not $cleaned) { exit 1 };exit 0
}
if($PlanPath) { throw 'Unexpected plan argument' }
Capacity 3072
if(Test-Path -LiteralPath $root) { throw 'Journal already exists' }
$ancestor=[IO.DirectoryInfo]$root
while($null -ne $ancestor) {
    if($ancestor.Exists -and ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint)) {throw 'Aliased temporary root'}
    $ancestor=$ancestor.Parent
}
[void](New-Item -ItemType Directory -Path $root)
$tool=$null
foreach($v in @(150,160)) { $candidate=Join-Path $env:ProgramFiles "Microsoft SQL Server\$v\Tools\Binn\SqlLocalDB.exe";if(Test-Path -LiteralPath $candidate) {$tool=$candidate;break} }
if(-not $tool) { throw 'Preinstalled LocalDB unavailable; no installation attempted' }
$versions=@(& $tool versions 2>$null);if($LASTEXITCODE) { throw 'LocalDB version unavailable' }
$selected=Select-TmSqlVersion $versions;$version=$selected.request
$existing=@(& $tool info 2>$null);if($LASTEXITCODE -or $instance -in $existing) { throw 'Instance scope already exists' }
Save-Json 'intent.json' @{nonce=$nonce;source=$env:GITHUB_SHA;instance=$instance;engineVersionRequested=$version;installedVersion=$selected.installed;syntheticOnly=$true;noSecrets=$true;newCharges=$false}
$created=$false;$startRequested=$false;$job=$null;$stopped=$false;$minimum=Free-MiB;$peak=0;$result=$null;$failure=$null
try {
    & $tool create $instance $version *> (Join-Path $root 'create.log');if($LASTEXITCODE) {throw 'Own creation failed'};$created=$true
    Capacity 3072;$startRequested=$true
    & $tool start $instance *> (Join-Path $root 'start.log');if($LASTEXITCODE) {throw 'Own start failed'}
    $connection=Open-OwnSql
    try {
        $identity=(Read-Sql $connection "SELECT CONVERT(int,SERVERPROPERTY('IsLocalDB')) AS localdb,CONVERT(int,SERVERPROPERTY('ProcessID')) AS pid,CONVERT(nvarchar(128),SERVERPROPERTY('ProductVersion')) AS version,c.net_transport FROM sys.dm_exec_connections c WHERE c.session_id=@@SPID;").Rows[0]
        if($identity.localdb -ne 1 -or $identity.net_transport -notin @('Named pipe','Shared memory') -or $identity.version -cne $selected.installed) {throw 'Own engine identity mismatch'}
        Exec-Sql $connection "EXEC sp_configure 'show advanced options',1;RECONFIGURE;EXEC sp_configure 'max server memory (MB)',256;RECONFIGURE;EXEC sp_configure 'max degree of parallelism',1;RECONFIGURE;"
        $limits=Read-Sql $connection "SELECT name,CONVERT(int,value_in_use) AS val FROM sys.configurations WHERE name IN('max server memory (MB)','max degree of parallelism');"
        foreach($setting in $limits.Rows) {if(($setting.name -eq 'max server memory (MB)' -and $setting.val -ne 256) -or ($setting.name -eq 'max degree of parallelism' -and $setting.val -ne 1)) {throw 'Own engine limits not applied'}}
    } finally {$connection.Dispose()}
    $owned=Get-Process -Id ([int]$identity.pid);$birth=$owned.StartTime
    $major=([string]$identity.version).Split('.')[0];$expectedEngine=Join-Path $env:ProgramFiles "Microsoft SQL Server\$($major)0\LocalDB\Binn\sqlservr.exe"
    if($owned.Path -ine $expectedEngine) {throw 'Unexpected engine executable'}
    Capacity 2048
    $clock=[Diagnostics.Stopwatch]::StartNew()
    $job=Start-Job -ScriptBlock {param($script,$plan) & $script -Worker -PlanPath $plan} -ArgumentList $PSCommandPath,$expectedPlan
    while($job.State -eq 'Running') {
        $free=Free-MiB;$minimum=[Math]::Min($minimum,$free);$current=Get-Process -Id $owned.Id
        if($current.StartTime -ne $birth -or $current.Path -ine $expectedEngine) {throw 'Engine identity changed'}
        $rss=[int]($current.WorkingSet64/1MB);$peak=[Math]::Max($peak,$rss)
        if($free -lt 1100 -or $rss -gt 768 -or $clock.Elapsed.TotalSeconds -gt 90) {throw 'Own runtime resource guard'}
        Start-Sleep -Milliseconds 250
    }
    [void](Receive-Job -Job $job -ErrorAction SilentlyContinue)
    $result=Get-Content -LiteralPath (Join-Path $root 'worker-result.json') -Raw -Encoding UTF8|ConvertFrom-Json
} catch { $failure=@{failureType=$_.Exception.GetType().Name} }
finally {
    if($null -ne $job) {if($job.State -eq 'Running') {Stop-Job -Job $job};Remove-Job -Job $job}
    if($startRequested) {
        & $tool stop $instance *> (Join-Path $root 'stop.log')
        $info=@(& $tool info $instance 2>$null);$stopped=($LASTEXITCODE -eq 0 -and [bool]($info -match '^State:\s+Stopped\s*$'))
    }
    $receipt=@{source=$env:GITHUB_SHA;nonce=$nonce;engineVersionRequested=$version;installedVersion=$selected.installed;engineStoppedVerified=$stopped;minimumAvailableMiB=$minimum;peakOwnSqlMiB=$peak;result=$result;failure=$failure;fullApplicationAccepted=$false;localRestoredCopyTested=$false;newCharges=$false}
    Save-Json 'receipt.json' $receipt
    Write-Output ('SQL_CONTEXT_RECEIPT '+($receipt|ConvertTo-Json -Depth 12 -Compress))
}
if(-not $stopped -or $null -eq $result -or -not $result.matrixCompleted -or -not $result.databaseCleanupVerified -or $null -ne $failure) {exit 1}
