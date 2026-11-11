<#
  Scrapes every game a team has played on basketaki.com: the team's results page,
  then each game's box score (player stats for BOTH teams) and quarter scores.

  Writes:
    data\games.csv          one row per game, from the team's point of view
    data\player_stats.csv   one row per player per game (both teams)
    data\stats.json         everything combined (used by the website)

  Usage (from this folder):
    powershell -ExecutionPolicy Bypass -File .\scrape_basketaki.ps1
    powershell -ExecutionPolicy Bypass -File .\scrape_basketaki.ps1 -Team athens-pistols -Refresh

  Box-score pages are cached in data\cache, so re-runs only download new games.
  Use -Refresh to re-download everything.
#>
param(
  [string]$Team = 'athens-pistols',
  [string]$OutDir = (Join-Path $PSScriptRoot 'data'),
  [int]$DelayMs = 600,
  [int]$MaxGames = 0,
  [switch]$Refresh,
  [string]$SiteDir = (Join-Path $PSScriptRoot 'site')
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Base = 'https://www.basketaki.com'
$CacheDir = Join-Path $OutDir 'cache'
New-Item -ItemType Directory -Force -Path $OutDir, $CacheDir | Out-Null
$RX = [System.Text.RegularExpressions.RegexOptions]::Singleline

function Get-Page([string]$Path, [switch]$NoCache) {
  # short file names: Windows paths over 260 characters fail
  $md5 = [Security.Cryptography.MD5]::Create()
  $hash = (-join ($md5.ComputeHash([Text.Encoding]::UTF8.GetBytes($Path)) | ForEach-Object { $_.ToString('x2') })).Substring(0, 10)
  $stub = ($Path.Trim('/') -replace '^games/', '' -replace '/box-score$', '' -replace '[^A-Za-z0-9\-]+', '_')
  if ($stub.Length -gt 24) { $stub = $stub.Substring(0, 24) }
  $file = Join-Path $CacheDir "$stub-$hash.html"
  if (-not $NoCache -and -not $Refresh -and (Test-Path $file)) {
    return [IO.File]::ReadAllText($file, [Text.Encoding]::UTF8)
  }
  $wc = New-Object System.Net.WebClient
  $wc.Encoding = [Text.Encoding]::UTF8
  $wc.Headers.Add('User-Agent', 'Mozilla/5.0 (team stats archive script)')
  $html = $wc.DownloadString($Base + $Path)
  Start-Sleep -Milliseconds $DelayMs
  # Only cache pages that actually contain player stats, so a box score that is
  # uploaded late gets picked up on the next run.
  if (-not $NoCache -and $html -match 'alc-name') {
    [IO.File]::WriteAllText($file, $html, (New-Object Text.UTF8Encoding $false))
  }
  return $html
}

function Clean([string]$s) {
  $s = $s -replace '<[^>]+>', ' '
  $s = [System.Net.WebUtility]::HtmlDecode($s)
  return ($s -replace '\s+', ' ').Trim()
}

function ToInt($s) {
  $s = "$s".Trim()
  if ($s -match '^-?\d+$') { return [int]$s }
  return $null
}

function ToMinutes($s) {
  $s = "$s".Trim()
  if ($s -match '^\d+$') { return [int]$s }
  if ($s -match '^(\d+):(\d+)$') { return [math]::Round([int]$Matches[1] + [int]$Matches[2] / 60, 1) }
  return $null
}

function Split-Shots($s) {
  if ("$s" -match '(\d+)\s*/\s*(\d+)') { return @([int]$Matches[1], [int]$Matches[2]) }
  return @($null, $null)
}

function Get-Cells([string]$rowHtml) {
  return @([regex]::Matches($rowHtml, '<t[dh](?:\s[^>]*)?>(.*?)</t[dh]>', $RX) | ForEach-Object { $_.Groups[1].Value })
}

function ToIsoDate([string]$d) {
  if ($d -match '(\d{2})/(\d{2})/(\d{4})') { return "$($Matches[3])-$($Matches[2])-$($Matches[1])" }
  return $d
}

# ---------------------------------------------------------------- results page
Write-Host "Fetching results page for $Team ..."
$resultsHtml = Get-Page "/teams/$Team/results" -NoCache

$teamName = $Team
if ($resultsHtml -match '<title>\s*(.*?)\s+-\s+Basketaki') { $teamName = Clean $Matches[1] }

$games = New-Object System.Collections.Generic.List[object]
$seen = @{}
foreach ($m in [regex]::Matches($resultsHtml, '<tr(?:\s[^>]*)?>(.*?)</tr>', $RX)) {
  $tr = $m.Groups[1].Value
  if ($tr -notmatch '<td class="team-result__date') { continue }   # skips the header row
  $c = Get-Cells $tr
  if ($c.Count -lt 8) { continue }

  $oppSlug = $null; if ($c[1] -match 'href="/teams/([^/"]+)/profile"') { $oppSlug = $Matches[1] }
  $gameSlug = $null; if ($c[7] -match 'href="/games/([^"]+)"') { $gameSlug = $Matches[1] }
  $opp = Clean $c[1]
  $homeAway = Clean $c[4]
  $hs = $null; $as = $null
  if ((Clean $c[3]) -match '^(\S+)\s*-\s*(\S+)$') { $hs = ToInt $Matches[1]; $as = ToInt $Matches[2] }
  $isHome = $homeAway -eq 'Home'
  $ts = if ($isHome) { $hs } else { $as }
  $os = if ($isHome) { $as } else { $hs }

  $key = if ($gameSlug) { $gameSlug } else { "$($c[0])|$opp" }
  if ($seen.ContainsKey($key)) { continue }
  $seen[$key] = $true

  $games.Add([pscustomobject][ordered]@{
    game_id      = $gameSlug
    date         = ToIsoDate (Clean $c[0])
    season       = Clean $c[6]
    competition  = Clean $c[5]
    round        = $null
    tournament   = $null
    opponent     = $opp
    opponent_id  = $oppSlug
    home_away    = $homeAway
    result       = Clean $c[2]
    team_score   = $ts
    opp_score    = $os
    margin       = $(if ($null -ne $ts -and $null -ne $os) { $ts - $os } else { $null })
    status       = 'played'
    forfeit      = $false
    team_q1 = $null; team_q2 = $null; team_q3 = $null; team_q4 = $null; team_ot = $null
    opp_q1  = $null; opp_q2  = $null; opp_q3  = $null; opp_q4  = $null; opp_ot  = $null
    has_box_score = $false
    team_players  = 0
    box_score_complete = $false
    url         = $(if ($gameSlug) { "$Base/games/$gameSlug" } else { $null })
  })
}
$games = @($games | Sort-Object date)
Write-Host "Found $($games.Count) games."
if ($MaxGames -gt 0) { $games = @($games | Select-Object -Last $MaxGames) }

# ---------------------------------------------------------------- box scores
$players = New-Object System.Collections.Generic.List[object]
$expectedHeaderCount = 19
$i = 0
foreach ($g in $games) {
  $i++
  # games with no W/L (byes, cancelled games) are kept but flagged
  if ($g.result -eq '') { $g.result = $null }
  if ($null -eq $g.result -or ($null -eq $g.team_score -and $null -eq $g.opp_score)) { $g.status = 'no result' }
  if (-not $g.game_id) {
    Write-Host ("[{0,3}/{1}] {2} {3,-28} (no game page)" -f $i, $games.Count, $g.date, $g.opponent)
    continue
  }

  try { $html = Get-Page "/games/$($g.game_id)/box-score" }
  catch { Write-Warning "Could not fetch $($g.game_id): $($_.Exception.Message)"; continue }

  if ($html -match '<h6 class="title noCap">(.*?)</h6>') {
    $g.tournament = Clean $Matches[1]
    # round number only from "<N>eta Agonistiki" (matchday, e.g. "5h Agonistiki" in Greek);
    # knockout rounds ("Round of 32") stay empty. Greek eta built from its code so the
    # script stays pure ASCII (Windows PowerShell 5.1 misreads non-ASCII in BOM-less files).
    $roundPattern = '(\d+)' + [char]0x03B7 + '\s'
    if ($g.tournament -match $roundPattern) { $g.round = [int]$Matches[1] }
  }

  # quarter scoreboard: first row = home team, second = away team
  $sb = [regex]::Match($html, '<table class="table table__cell-center[^"]*"[^>]*>(.*?)</table>', $RX)
  if ($sb.Success) {
    $sbRows = @([regex]::Matches($sb.Groups[1].Value, '<tr(?:\s[^>]*)?>(.*?)</tr>', $RX) | ForEach-Object { , @(Get-Cells $_.Groups[1].Value | ForEach-Object { Clean $_ }) })
    $data = @($sbRows | Where-Object { $_[0] -notmatch '(?i)^scoreboard$' })
    if ($data.Count -ge 2) {
      $homeRow = $data[0]; $awayRow = $data[1]
      $tRow = if ($g.home_away -eq 'Home') { $homeRow } else { $awayRow }
      $oRow = if ($g.home_away -eq 'Home') { $awayRow } else { $homeRow }
      $g.team_q1 = ToInt $tRow[1]; $g.team_q2 = ToInt $tRow[2]; $g.team_q3 = ToInt $tRow[3]; $g.team_q4 = ToInt $tRow[4]; $g.team_ot = ToInt $tRow[5]
      $g.opp_q1  = ToInt $oRow[1]; $g.opp_q2  = ToInt $oRow[2]; $g.opp_q3  = ToInt $oRow[3]; $g.opp_q4  = ToInt $oRow[4]; $g.opp_ot  = ToInt $oRow[5]
    }
  }

  $tables = [regex]::Matches($html, '<table class="[^"]*alc-table-stats[^"]*"[^>]*>(.*?)</table>', $RX)
  $gameLines = New-Object System.Collections.Generic.List[object]
  foreach ($t in $tables) {
    # team = last team-name link before this table (the card header)
    $before = $html.Substring(0, $t.Index)
    $nm = [regex]::Matches($before, 'team-meta__name[^"]*">\s*<a href="/teams/([^/"]+)/profile"[^>]*>(.*?)</a>', $RX)
    $tSlug = $null; $tName = $null
    if ($nm.Count -gt 0) { $last = $nm[$nm.Count - 1]; $tSlug = $last.Groups[1].Value; $tName = Clean $last.Groups[2].Value }
    $isTeam = $tSlug -eq $Team

    $rows = [regex]::Matches($t.Groups[1].Value, '<tr(?:\s[^>]*)?>(.*?)</tr>', $RX)
    foreach ($r in $rows) {
      $rh = $r.Groups[1].Value
      if ($rh -match '<th[\s>]') {
        $hc = (Get-Cells $rh).Count
        if ($hc -ne $expectedHeaderCount) { Write-Warning "$($g.game_id): unexpected header with $hc columns" }
        continue
      }
      if ($rh -notmatch 'alc-name') { continue }   # skips the totals row
      $c = Get-Cells $rh
      if ($c.Count -lt $expectedHeaderCount) { Write-Warning "$($g.game_id): short row ($($c.Count) cells)"; continue }

      $pSlug = $null; if ($c[0] -match 'href="/players/([^"]+)"') { $pSlug = $Matches[1] }
      $ft = Split-Shots (Clean $c[12]); $p2 = Split-Shots (Clean $c[14]); $p3 = Split-Shots (Clean $c[16])

      $gameLines.Add([pscustomobject][ordered]@{
        game_id     = $g.game_id
        date        = $g.date
        season      = $g.season
        competition = $g.competition
        team_id     = $tSlug
        team        = $tName
        is_our_team = $isTeam
        opponent    = $(if ($isTeam) { $g.opponent } else { $teamName })
        player_id   = $pSlug
        player      = Clean $c[0]
        mvp         = [bool]($c[1] -match 'fa-trophy')
        min         = ToMinutes (Clean $c[2])
        pts         = ToInt (Clean $c[3])
        eff         = ToInt (Clean $c[4])
        reb         = ToInt (Clean $c[5])
        oreb        = ToInt (Clean $c[6])
        dreb        = ToInt (Clean $c[7])
        ast         = ToInt (Clean $c[8])
        stl         = ToInt (Clean $c[9])
        tov         = ToInt (Clean $c[10])
        blk         = ToInt (Clean $c[11])
        ftm         = $ft[0];  fta  = $ft[1]
        fg2m        = $p2[0];  fg2a = $p2[1]
        fg3m        = $p3[0];  fg3a = $p3[1]
        tmr         = ToInt (Clean $c[18])
      })
    }
  }

  # drop did-not-play rows (0 minutes and no stats at all)
  $kept = @($gameLines | Where-Object {
    $_.min -gt 0 -or $_.pts -or $_.reb -or $_.ast -or $_.stl -or $_.tov -or $_.blk -or $_.fta -or $_.fg2a -or $_.fg3a
  })
  # forfeits: 20-0 result and nobody scored in the box score -> keep the game, no player lines
  $isForfeitScore = ($g.team_score -eq 20 -and $g.opp_score -eq 0) -or ($g.team_score -eq 0 -and $g.opp_score -eq 20)
  $boxPts = ($kept | Measure-Object pts -Sum).Sum
  if ($isForfeitScore -and -not $boxPts) { $kept = @(); $g.status = 'forfeit'; $g.forfeit = $true }

  foreach ($l in $kept) { $players.Add($l) }
  $ours = @($kept | Where-Object is_our_team)
  $g.has_box_score = $ours.Count -gt 0
  $g.team_players = $ours.Count
  $ourPts = ($ours | Measure-Object pts -Sum).Sum
  $g.box_score_complete = $g.has_box_score -and ($ourPts -eq $g.team_score)
  Write-Host ("[{0,3}/{1}] {2} {3,-28} {4,-2} {5,7}  players: {6}" -f $i, $games.Count, $g.date, $g.opponent, $g.result, "$($g.team_score)-$($g.opp_score)", $kept.Count)
}

# ---------------------------------------------------------------- sanity check
$mismatch = 0
foreach ($g in ($games | Where-Object { $_.status -eq 'played' -and -not $_.box_score_complete })) {
  $mismatch++
  $sum = ($players | Where-Object { $_.game_id -eq $g.game_id -and $_.is_our_team } | Measure-Object pts -Sum).Sum
  Write-Host ("  incomplete box score on site: {0} vs {1} - player points {2}, final score {3}" -f $g.date, $g.opponent, [int]$sum, $g.team_score)
}

# ---------------------------------------------------------------- output
$csvGames = Join-Path $OutDir 'games.csv'
$csvPlayers = Join-Path $OutDir 'player_stats.csv'
$games | Export-Csv -Path $csvGames -NoTypeInformation -Encoding UTF8
$players | Export-Csv -Path $csvPlayers -NoTypeInformation -Encoding UTF8

$json = [ordered]@{
  team_id    = $Team
  team       = $teamName
  source     = "$Base/teams/$Team/results"
  scraped_at = (Get-Date).ToString('s')
  games      = $games
  players    = $players
} | ConvertTo-Json -Depth 5 -Compress
[IO.File]::WriteAllText((Join-Path $OutDir 'stats.json'), $json, (New-Object Text.UTF8Encoding $false))

# website data: site\data.js is loaded by site\index.html (works when opened straight from disk)
if ($SiteDir) {
  New-Item -ItemType Directory -Force -Path $SiteDir | Out-Null
  [IO.File]::WriteAllText((Join-Path $SiteDir 'data.js'), "window.PISTOLS_DATA = $json;`n", (New-Object Text.UTF8Encoding $false))
  Write-Host "Website data updated: $(Join-Path $SiteDir 'data.js')"
}

$withBox = @($games | Where-Object has_box_score).Count
Write-Host ""
Write-Host "Done. $($games.Count) games, $withBox with box scores, $($players.Count) player lines. Point-sum mismatches: $mismatch"
Write-Host "Saved: $csvGames"
Write-Host "       $csvPlayers"
Write-Host "       $(Join-Path $OutDir 'stats.json')"
