Set-StrictMode -Version Latest

function Assert-TmSqlRequest([hashtable]$Request) {
    if ($Request.actions -cne 'true' -or $Request.repository -cne 'Ahgarzon/tm-apk' -or
        $Request.public -ine 'true' -or $Request.actorId -cne '114458437' -or
        $Request.sha -cnotmatch '^[a-f0-9]{40}$' -or $Request.expectedSha -cne $Request.sha -or
        $Request.nonce -cnotmatch '^[a-f0-9]{32}$') { throw 'Request boundary rejected' }
}

function Assert-TmSqlIdentifier([string]$Value, [string]$Nonce, [string]$Kind) {
    if ($Nonce -cnotmatch '^[a-f0-9]{32}$') { throw 'Invalid nonce' }
    $prefix = 'TmSql_' + $Nonce.Substring(0,16)
    $allowed = if ($Kind -eq 'instance') { @($prefix) } elseif ($Kind -eq 'database') {
        @(0..3 | ForEach-Object { $prefix + '_c' + $_ })
    } else { throw 'Invalid resource kind' }
    if ($Value -cnotin $allowed) { throw 'Unowned SQL target rejected' }
}

function Select-TmSqlVersion([string[]]$Lines) {
    $versions = @($Lines | ForEach-Object {
        $match=[regex]::Match($_,'\b(15|16)\.\d+\.\d+\.\d+\b')
        if($match.Success) {$match.Value}
    })
    foreach($major in @('15','16')) {
        $selected=@($versions | Where-Object {$_.StartsWith($major+'.')} | Select-Object -First 1)
        if($selected.Count) {return @{request=$major+'.0';installed=$selected[0]}}
    }
    throw 'Reviewed engine major unavailable'
}
