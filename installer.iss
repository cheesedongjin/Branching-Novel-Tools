; installer.iss - Online Bootstrap Installer

#ifndef InstallEditor
  #define InstallEditor 1
#endif
#ifndef InstallGame
  #define InstallGame 1
#endif
#ifndef MyAppName
  #define MyAppName "MyApp"
#endif
#ifndef MyAppExe
  #define MyAppExe "MyApp.exe"
#endif
#ifndef GitHubRepo
  #define GitHubRepo "cheesedongjin/Branching-Novel-Tools"
#endif
#ifndef ReleaseAssetPattern
  #define ReleaseAssetPattern ""
#endif

; ★ GUID는 맨몸(하이픈 포함, 중괄호 없음)으로만 정의
#ifndef MyAppGuid
  #define MyAppGuid "B1C50C47-7B73-4308-9C74-2A9B3E11A9D3"
#endif

; 파생: Setup용(이중중괄호), 코드/레지스트리용(단일중괄호)
#define MyAppIdSetup "{{" + MyAppGuid + "}}"
#define MyAppIdReg   "{"  + MyAppGuid + "}"

[Setup]
AppId={#MyAppIdSetup}
AppName={#MyAppName}
AppVersion={code:GetAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
Compression=lzma2
CreateUninstallRegKey=yes
ChangesAssociations=yes
SolidCompression=yes
OutputBaseFilename={#MyAppName}-Online-Setup
WizardStyle=modern
; Use the modern 64-bit identifier to avoid deprecation warnings.
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExe}
SetupLogging=yes
#if (InstallEditor) && (!InstallGame)
  #ifexist "assets\icons\editor.ico"
  SetupIconFile=assets\icons\editor.ico
  #endif
#else
  #ifexist "assets\icons\app.ico"
  SetupIconFile=assets\icons\app.ico
  #endif
#endif
LanguageDetectionMethod=uilanguage
UsePreviousLanguage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[CustomMessages]
english.AssociateBnov=Associate .bnov files with {#MyAppName}
korean.AssociateBnov=.bnov 파일을 {#MyAppName}에 연결

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
#if InstallGame
Name: "fileassoc"; Description: "{cm:AssociateBnov}"; Flags: checkedonce
#endif

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Registry]
#if InstallGame
; ----------
; 파일 연결(ProgID) - 관리자 설치: HKCR/HKLM
; ----------
Root: HKCR; Subkey: ".bnov"; ValueType: string; ValueName: ""; ValueData: "BranchingNovelFile"; Flags: uninsdeletevalue; Tasks: fileassoc; Check: IsAdminLoggedOn
Root: HKCR; Subkey: "BranchingNovelFile"; ValueType: string; ValueName: ""; ValueData: "Branching Novel Script"; Flags: uninsdeletekey; Tasks: fileassoc; Check: IsAdminLoggedOn
Root: HKCR; Subkey: "BranchingNovelFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExe},0"; Tasks: fileassoc; Check: IsAdminLoggedOn
Root: HKCR; Subkey: "BranchingNovelFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExe}"" ""%1"""; Tasks: fileassoc; Check: IsAdminLoggedOn

; ----------
; 파일 연결(ProgID) - 사용자 설치: HKCU\Software\Classes
; ----------
Root: HKCU; Subkey: "Software\Classes\.bnov"; ValueType: string; ValueName: ""; ValueData: "BranchingNovelFile"; Flags: uninsdeletevalue; Tasks: fileassoc; Check: not IsAdminLoggedOn
Root: HKCU; Subkey: "Software\Classes\BranchingNovelFile"; ValueType: string; ValueName: ""; ValueData: "Branching Novel Script"; Flags: uninsdeletekey; Tasks: fileassoc; Check: not IsAdminLoggedOn
Root: HKCU; Subkey: "Software\Classes\BranchingNovelFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExe},0"; Tasks: fileassoc; Check: not IsAdminLoggedOn
Root: HKCU; Subkey: "Software\Classes\BranchingNovelFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExe}"" ""%1"""; Tasks: fileassoc; Check: not IsAdminLoggedOn

; ----------
; 기본 앱 UI 노출(Capabilities) - 관리자 설치(HKLM)
; ----------
Root: HKLM; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: "Software\{#MyAppName}\Capabilities"; Flags: uninsdeletevalue; Check: IsAdminLoggedOn
Root: HKLM; Subkey: "Software\{#MyAppName}\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#MyAppName}"; Check: IsAdminLoggedOn
Root: HKLM; Subkey: "Software\{#MyAppName}\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "{#MyAppName} can open Branching Novel Script files (.bnov)"; Check: IsAdminLoggedOn
Root: HKLM; Subkey: "Software\{#MyAppName}\Capabilities\FileAssociations"; ValueType: string; ValueName: ".bnov"; ValueData: "BranchingNovelFile"; Check: IsAdminLoggedOn

; ----------
; 기본 앱 UI 노출(Capabilities) - 사용자 설치(HKCU)
; ----------
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: "Software\{#MyAppName}\Capabilities"; Flags: uninsdeletevalue; Check: not IsAdminLoggedOn
Root: HKCU; Subkey: "Software\{#MyAppName}\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#MyAppName}"; Check: not IsAdminLoggedOn
Root: HKCU; Subkey: "Software\{#MyAppName}\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "{#MyAppName} can open Branching Novel Script files (.bnov)"; Check: not IsAdminLoggedOn
Root: HKCU; Subkey: "Software\{#MyAppName}\Capabilities\FileAssociations"; ValueType: string; ValueName: ".bnov"; ValueData: "BranchingNovelFile"; Check: not IsAdminLoggedOn
#endif

; ----------
; 업데이트용: 버전 정보를 고정 경로(HKCU)에 저장
; ----------
Root: HKCU; Subkey: "Software\BranchingNovelTools\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{code:GetAppVersion}"; Flags: uninsdeletekey

[UninstallDelete]
; Remove all files and subfolders in app directory
Type: filesandordirs; Name: "{app}\*"

; Remove installation log as well
Type: files; Name: "{app}\install.log"

[Code]
var
  GLatestVersion: String;
  GPayloadZipURL: String;
  GPayloadShaURL: String;

function IsPSAvailable(): Boolean;
var
  ResultCode: Integer;
begin
  Result :=
    Exec('powershell.exe',
         '-NoLogo -NoProfile -Command "$PSVersionTable.PSVersion.Major | Out-Null"',
         '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
    and (ResultCode = 0);
end;

procedure EnsureParentDirExists(const FilePath: String);
var
  Dir: String;
begin
  Dir := ExtractFilePath(FilePath);
  if (Dir <> '') and (not DirExists(Dir)) then
    CreateDir(Dir);
end;

function SafeAddToLog(const LogPath, Line: String): Boolean;
begin
  EnsureParentDirExists(LogPath);
  Result := SaveStringToFile(LogPath, Line + #13#10, True);
end;

function EscapeForSingleQuotes(const S: String): String;
var
  R: String;
begin
  R := S;
  StringChange(R, '''', '''''');  { ' -> '' }
  Result := R;
end;

{ Quoting for PowerShell strings: always wrap in single quotes and escape internal ' }
function PSQuote(const S: String): String;
begin
  Result := '''' + EscapeForSingleQuotes(S) + '''';
end;

function MakeTempScriptFile(const Hint: String): String;
begin
  repeat
    Result := ExpandConstant(
      '{tmp}\installer_' + Hint + '_' + IntToStr(Random(2147483647)) + '.ps1'
    );
  until not FileExists(Result);
end;

function WriteAndRunPS(const Cmd, LogPath, ScriptNameHint: String): Boolean;
var
  ResultCode: Integer;
  PSExe, PSArgs, ScriptPath, ScriptBody, EscapedCmd, TranscriptPath: String;
  StartOk: Boolean;
begin
  Result := False;

  EnsureParentDirExists(LogPath);
  SafeAddToLog(LogPath, '---');
  SafeAddToLog(LogPath, 'CREATE PS SCRIPT FOR: ' + ScriptNameHint);

  PSExe := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
  if not FileExists(PSExe) then
    PSExe := 'powershell.exe';

  ScriptPath := MakeTempScriptFile(ScriptNameHint);
  TranscriptPath := ExpandConstant('{tmp}\ps_transcript_' + ScriptNameHint + '_' + IntToStr(Random(2147483647)) + '.txt');
  EscapedCmd := EscapeForSingleQuotes(Cmd);

  ScriptBody :=
    '$ErrorActionPreference = ''Stop'';' + #13#10 +
    '$Log = ' + PSQuote(LogPath) + ';' + #13#10 +
    '$Transcript = ' + PSQuote(TranscriptPath) + ';' + #13#10 +
    'function Write-Log($s){' + #13#10 +
    '  try { Add-Content -LiteralPath $Log -Value $s } catch {}' + #13#10 +
    '}' + #13#10 +
    'Write-Log ("SCRIPT PATH: ' + EscapeForSingleQuotes(ScriptPath) + '");' + #13#10 +
    'Write-Log ("SCRIPT BODY BEGIN >>>");' + #13#10 +
    'Write-Log ' + PSQuote(Cmd) + ';' + #13#10 +
    'Write-Log ("<<< SCRIPT BODY END");' + #13#10 +
    'try {' + #13#10 +
    '  Start-Transcript -Path $Transcript -ErrorAction SilentlyContinue | Out-Null' + #13#10 +
    '  Write-Log ''CMD: ' + EscapedCmd + ''';' + #13#10 +
    '  ' + Cmd + #13#10 +
    '  Write-Log ''OK'';' + #13#10 +
    '} catch {' + #13#10 +
    '  Write-Log (''ERROR: '' + $_.Exception.ToString());' + #13#10 +
    '  if ($_.InvocationInfo -ne $null) {' + #13#10 +
    '    Write-Log (''AT: '' + $_.InvocationInfo.PositionMessage)' + #13#10 +
    '    Write-Log (''SCRIPTNAME: '' + $_.InvocationInfo.ScriptName)' + #13#10 +
    '    Write-Log (''LINE: '' + $_.InvocationInfo.ScriptLineNumber)' + #13#10 +
    '  }' + #13#10 +
    '  Write-Log (''LASTEXITCODE: '' + $LASTEXITCODE)' + #13#10 +
    '  exit 1' + #13#10 +
    '} finally {' + #13#10 +
    '  try { Stop-Transcript | Out-Null } catch {}' + #13#10 +
    '  try { if (Test-Path -LiteralPath $Transcript) { Write-Log (''TRANSCRIPT: '' + $Transcript) } } catch {}' + #13#10 +
    '}' ;

  EnsureParentDirExists(ScriptPath);
  if not SaveStringToFile(ScriptPath, ScriptBody, False) then
  begin
    SafeAddToLog(LogPath, 'ERROR: Failed to create PS script at ' + ScriptPath);
    Exit;
  end;

  PSArgs := '-NoLogo -NoProfile -ExecutionPolicy Bypass -File ';
  StartOk := Exec(PSExe, PSArgs + AddQuotes(ScriptPath), '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  if not StartOk then
  begin
    SafeAddToLog(LogPath, 'PS START ERROR code=' + IntToStr(ResultCode) + ' msg=' + SysErrorMessage(ResultCode));
    Exit;
  end;

  if ResultCode <> 0 then
  begin
    SafeAddToLog(LogPath, 'PS EXIT CODE=' + IntToStr(ResultCode));
    SafeAddToLog(LogPath, 'PS SCRIPT AT: ' + ScriptPath);
    { 스크립트 전문도 저장(문제 재현에 유용) }
    SafeAddToLog(LogPath, 'PS SCRIPT CONTENT BEGIN >>>');
    SafeAddToLog(LogPath, ScriptBody);
    SafeAddToLog(LogPath, '<<< PS SCRIPT CONTENT END');
    Exit;
  end;

  Result := True;
end;

function ResolveLatestRelease(const LogPath: String): Boolean;
var
  Cmd, OutPath, Part: String;
  ContentAnsi: AnsiString;
begin
  if GPayloadZipURL <> '' then
  begin
    Result := True;
    Exit;
  end;
  Result := False;
  OutPath := ExpandConstant('{tmp}\\latest_release.txt');
  Cmd :=
    '$ErrorActionPreference = ''Stop''; ' +
    '[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; ' +
    '$resp = Invoke-WebRequest -Uri ' + PSQuote('https://api.github.com/repos/{#GitHubRepo}/releases/latest') + '; ' +
    '$json = $resp.Content | ConvertFrom-Json; ' +
    '$tag = $json.tag_name; ' +
    '$ver = if($tag -and $tag.StartsWith("v")) { $tag.Substring(1) } else { $tag }; ' +
    '$zipAsset = $json.assets | Where-Object { $_.name -eq ' + PSQuote('latest-{#ReleaseAssetPattern}.zip') + ' } | Select-Object -First 1; ' +
    '$shaAsset = $json.assets | Where-Object { $_.name -eq ' + PSQuote('latest-{#ReleaseAssetPattern}.sha256') + ' } | Select-Object -First 1; ' +
    '$zip = $zipAsset.browser_download_url; ' +
    '$sha = $shaAsset.browser_download_url; ' +
    '$out = @($ver, $zip, $sha) -join "|"; ' +
    'Set-Content -LiteralPath ' + PSQuote(OutPath) + ' -Value $out -Encoding ASCII;';
  if not WriteAndRunPS(Cmd, LogPath, 'github_latest') then
    Exit;
  if not LoadStringFromFile(OutPath, ContentAnsi) then
    Exit;
  Part := Trim(String(ContentAnsi));
  if Pos('|', Part) = 0 then Exit;
  GLatestVersion := Copy(Part, 1, Pos('|', Part) - 1);
  Delete(Part, 1, Pos('|', Part));
  if Pos('|', Part) = 0 then Exit;
  GPayloadZipURL := Copy(Part, 1, Pos('|', Part) - 1);
  Delete(Part, 1, Pos('|', Part));
  GPayloadShaURL := Trim(Part);
  Result := (GLatestVersion <> '') and (GPayloadZipURL <> '') and (GPayloadShaURL <> '');
end;

function EnsureLatest(const LogPath: String): Boolean;
begin
  Result := ResolveLatestRelease(LogPath);
end;

function GetAppVersion(Param: String): String;
begin
  if GLatestVersion = '' then
    if not EnsureLatest(ExpandConstant('{tmp}\\latest.log')) then
      GLatestVersion := '0.0.0';
  Result := GLatestVersion;
end;

function DownloadAndVerify(const UrlZip, UrlSha, DestZip, DestSha, LogPath: String): Boolean;
var
  Cmd: String;
begin
  Cmd :=
    '$ErrorActionPreference = ''Stop''; ' +
    '[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; ' +
    'Invoke-WebRequest -Uri (' + PSQuote(UrlZip) + ' + ' + PSQuote('?cb=') + ' + [Guid]::NewGuid().ToString()) -OutFile ' + PSQuote(DestZip) + '; ' +
    'Invoke-WebRequest -Uri (' + PSQuote(UrlSha) + ' + ' + PSQuote('?cb=') + ' + [Guid]::NewGuid().ToString()) -OutFile ' + PSQuote(DestSha) + '; ' +
    '$expected = (Get-Content -LiteralPath ' + PSQuote(DestSha) + ' | Select-Object -First 1).Split('' '')[0]; ' +
    'if ([string]::IsNullOrWhiteSpace($expected)) { throw ''Empty SHA file'' } ' +
    '$actual = (Get-FileHash -LiteralPath ' + PSQuote(DestZip) + ' -Algorithm SHA256).Hash.ToLower(); ' +
    'if ($expected.ToLower() -ne $actual) { throw (''Hash mismatch. Expected: '' + $expected + '', Actual: '' + $actual) }';

  Result := WriteAndRunPS(Cmd, LogPath, 'download_verify');
end;

function ExpandZipToApp(const ZipPath, TargetDir, LogPath: String): Boolean;
var
  Cmd: String;
begin
  Cmd :=
    '$ErrorActionPreference = ''Stop''; ' +
    '$zip = ' + PSQuote(ZipPath) + '; ' +
    '$target = ' + PSQuote(TargetDir) + '; ' +
    '$temp = Join-Path $env:TEMP (''payload_'' + [guid]::NewGuid().ToString()); ' +

    'function Write-Log($s){ try{ Add-Content -LiteralPath ' + PSQuote(LogPath) + ' -Value $s } catch{} } ' +

    'Write-Log "STEP: Create temp dir"; ' +
    'New-Item -ItemType Directory -Path $temp -Force | Out-Null; ' +

    'Write-Log "STEP: Add-Type System.IO.Compression.FileSystem"; ' +
    'try { Add-Type -AssemblyName System.IO.Compression.FileSystem } ' +
    'catch { Write-Log ("ERROR Add-Type: " + $_.Exception.Message); throw } ' +

    'Write-Log ("STEP: Extract " + $zip + " -> " + $temp); ' +
    '[System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $temp); ' +
    '$srcCount = (Get-ChildItem -LiteralPath $temp -Recurse -Force | Where-Object { -not $_.PSIsContainer }).Count; ' +
    'Write-Log ("EXTRACTED FILES: " + $srcCount); ' +
    'if ($srcCount -eq 0) { throw (''ZIP is empty after extract: '' + $zip) } ' +

    'Write-Log ("STEP: Ensure target exists -> " + $target); ' +
    'if (-not (Test-Path -LiteralPath $target)) { New-Item -ItemType Directory -Path $target -Force | Out-Null }; ' +

    'Write-Log "STEP: Kill running process"; ' +
    '$proc = [System.IO.Path]::GetFileNameWithoutExtension(' + PSQuote('{#MyAppExe}') + '); ' +
    'try{ Get-Process -Name $proc -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue }catch{ Write-Log("WARN kill " + $proc + ": " + $_.Exception.Message) } ' +
    'Start-Sleep -Milliseconds 400; ' +

    'Write-Log "STEP: Clear readonly attributes"; ' +
    'try{ attrib -R (Join-Path $target "*") /S }catch{ Write-Log("WARN attrib: " + $_.Exception.Message) } ' +

    'function Add-LongPrefix([string]$p){ if($p -like "\\\\?\\*"){ return $p } else { return ("\\\\?\\" + $p) } } ' +

    'Write-Log "STEP: Robocopy sync"; ' +
    '$robocopyPath = Join-Path $env:WINDIR "System32\\robocopy.exe"; ' +
    'if (-not (Test-Path -LiteralPath $robocopyPath)) { $robocopyPath = "robocopy.exe" } ' +
    '$robolog = Join-Path $env:TEMP (''robocopy_'' + [guid]::NewGuid().ToString() + ''.log''); ' +
    '$argLine = "`"$temp`" `"$target`" /E /R:2 /W:1 /NFL /NDL /NP /NJH /NJS /COPY:DAT /LOG:`"$robolog`""; ' +

    'function Try-Robocopy{ ' +
    '  param([int]$attempts) ' +
    '  for($i=1; $i -le $attempts; $i++){ ' +
    '    Write-Log("ROBOCOPY ARGLINE: " + $argLine); ' +
    '    $p = Start-Process -FilePath $robocopyPath -ArgumentList $argLine -NoNewWindow -PassThru -Wait; ' +
    '    $code = $p.ExitCode; ' +
    '    if($code -lt 8){ Write-Log ("ROBOCOPY OK code=" + $code + " attempt=" + $i); return $true } ' +
    '    Write-Log ("ROBOCOPY EXIT CODE: " + $code + " (attempt " + $i + ")"); ' +
    '    try{ $tail = Get-Content -LiteralPath $robolog -Tail 80 -Encoding UTF8 -ErrorAction SilentlyContinue; foreach($line in $tail){ Write-Log("ROBOCOPY: " + $line) } }catch{} ' +
    '    Start-Sleep -Milliseconds (300 * $i) ' +
    '  } ' +
    '  Write-Log("ROBOCOPY FAILED args=" + $argLine + " log=" + $robolog); ' +
    '  return $false ' +
    '} ' +

    'if(-not (Try-Robocopy -attempts 3)){ ' +
    '  Write-Log("STEP: Fallback per-file Copy-Item with retries"); ' +
    '  $items = Get-ChildItem -LiteralPath $temp -Recurse -File -Force; ' +
    '  foreach($it in $items){ ' +
    '    $rel = $it.FullName.Substring($temp.Length).TrimStart(''\\''); ' +
    '    $dest = Join-Path $target $rel; ' +
    '    $destDir = Split-Path -Parent $dest; if(-not (Test-Path -LiteralPath $destDir)){ New-Item -ItemType Directory -Path $destDir -Force | Out-Null } ' +
    '    $ok=$false; for($r=1; $r -le 3 -and -not $ok; $r++){ ' +
    '      try{ Copy-Item -LiteralPath (Add-LongPrefix($it.FullName)) -Destination (Add-LongPrefix($dest)) -Force -ErrorAction Stop; $ok=$true } ' +
    '      catch{ Write-Log("COPY FAIL("+$r+"): " + $it.FullName + " -> " + $dest + " :: " + $_.Exception.Message); Start-Sleep -Milliseconds (250*$r) } ' +
    '    } ' +
    '    if(-not $ok){ throw ("Copy failed: " + $it.FullName) } ' +
    '  } ' +
    '} ' +

    'Write-Log "STEP: Ensure expected exe"; ' +
    '$expectedExe = Join-Path $target ' + PSQuote('{#MyAppExe}') + '; ' +
    'if (-not (Test-Path -LiteralPath $expectedExe)) { ' +
    '  $found = Get-ChildItem -LiteralPath $target -Filter ' + PSQuote('{#MyAppExe}') + ' -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1; ' +
    '  if ($null -ne $found) { Move-Item -LiteralPath $found.FullName -Destination $expectedExe -Force } ' +
    '} ' +
    'if (-not (Test-Path -LiteralPath $expectedExe)) { throw ("Expected exe not found: " + $expectedExe + ". Check ZIP root & structure.") } ' +
    'Write-Log "STEP: Done"; ';

  Result := WriteAndRunPS(Cmd, LogPath, 'expand_zip');
end;

procedure UpdateVersionFromExe(const LogPath: String);
var
  ExePath, Version, UninstKey: String;
  RootKey: Integer;
begin
  ExePath := ExpandConstant('{app}\{#MyAppExe}');
  if GetVersionNumbersString(ExePath, Version) then
  begin
    RegWriteStringValue(HKCU, 'Software\BranchingNovelTools\{#MyAppName}', 'Version', Version);

    if IsAdminLoggedOn then
      RootKey := HKLM
    else
      RootKey := HKCU;
    UninstKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + '{#MyAppIdReg}' + '_is1';
    RegWriteStringValue(RootKey, UninstKey, 'DisplayVersion', Version);

    SafeAddToLog(LogPath, 'Version recorded: ' + Version);
  end
  else
    SafeAddToLog(LogPath, 'Version detection failed for ' + ExePath);
end;

{ SINGLE CurStepChanged: merge install-phase work and language-file writing }
procedure CurStepChanged(CurStep: TSetupStep);
var
  ZipPath, ShaPath, LogPath: String;
  Ok: Boolean;
  Lang, Base: String;
begin
  LogPath := ExpandConstant('{app}\install.log');
  if CurStep = ssInstall then
  begin

    if not IsPSAvailable() then
    begin
      SafeAddToLog(LogPath, 'PowerShell not found');
      MsgBox('PowerShell not found. Please run on Windows 10/11.', mbError, MB_OK);
      WizardForm.Close;
      Exit;
    end;

    SafeAddToLog(LogPath, 'BEGIN INSTALL');

    ZipPath := ExpandConstant('{tmp}\payload.zip');
    ShaPath := ExpandConstant('{tmp}\payload.sha256');

    WizardForm.StatusLabel.Caption := 'Downloading and verifying...';
    try
      WizardForm.ProgressGauge.Style := npbstMarquee;
    except
      WizardForm.ProgressGauge.Style := npbstNormal;
    end;

    if not EnsureLatest(LogPath) then
    begin
      WizardForm.ProgressGauge.Style := npbstNormal;
      MsgBox('Failed to resolve latest release info. See install.log.', mbError, MB_OK);
      WizardForm.Close;
      Exit;
    end;

    Ok := DownloadAndVerify(GPayloadZipURL, GPayloadShaURL, ZipPath, ShaPath, LogPath);
    if not Ok then
    begin
      WizardForm.ProgressGauge.Style := npbstNormal;
      MsgBox('Download or verification failed. See install.log.', mbError, MB_OK);
      WizardForm.Close;
      Exit;
    end;

    WizardForm.StatusLabel.Caption := 'Extracting...';
    Ok := ExpandZipToApp(ZipPath, ExpandConstant('{app}'), LogPath);
    WizardForm.ProgressGauge.Style := npbstNormal;

    if not Ok then
    begin
      MsgBox('Extraction failed. See install.log.', mbError, MB_OK);
      WizardForm.Close;
      Exit;
    end;

    SafeAddToLog(LogPath, 'END OK');
  end
  else if CurStep = ssPostInstall then
  begin
    UpdateVersionFromExe(LogPath);

    if ActiveLanguage = 'korean' then
      Lang := 'korean'
    else
      Lang := 'en';

    Base := ExpandConstant('{%USERPROFILE}\.branching_novel\');
    ForceDirectories(Base);
    SaveStringToFile(Base + 'language.txt', Lang, False);
#if InstallEditor
    SaveStringToFile(Base + 'editor_language.txt', Lang, False);
#endif
#if InstallGame
    SaveStringToFile(Base + 'game_language.txt', Lang, False);
#endif
  end;
end;
