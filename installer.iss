; installer.iss - Online Bootstrap Installer

#ifndef MyAppName
  #define MyAppName "MyApp"
#endif
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#ifndef MyAppExe
  #define MyAppExe "MyApp.exe"
#endif
#ifndef PayloadZipURL
  #define PayloadZipURL "https://example.com/latest.zip"
#endif
#ifndef PayloadShaURL
  #define PayloadShaURL "https://example.com/latest.sha256"
#endif

[Setup]
AppId={{B1C50C47-7B73-4308-9C74-2A9B3E11A9D3}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
Compression=lzma2
CreateUninstallRegKey=yes
ChangesAssociations=yes
SolidCompression=yes
OutputBaseFilename={#MyAppName}-Online-Setup
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExe}
SetupLogging=yes
#ifexist "assets\icons\app.ico"
SetupIconFile=assets\icons\app.ico
#endif
LanguageDetectionMethod=uilanguage
UsePreviousLanguage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "fileassoc"; Description: "Associate .bnov files with {#MyAppName}"; Flags: checkedonce

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Registry]
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

; ----------
; 업데이트용: 버전 정보를 고정 경로(HKCU)에 저장
; ----------
Root: HKCU; Subkey: "Software\BranchingNovelTools\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey

[UninstallDelete]
; Remove all files and subfolders in app directory
Type: filesandordirs; Name: "{app}\*"

; Remove installation log as well
Type: files; Name: "{app}\install.log"

[Code]
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
  PSExe, PSArgs, ScriptPath, ScriptBody, EscapedCmd: String;
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
  EscapedCmd := EscapeForSingleQuotes(Cmd);

  ScriptBody :=
    '$ErrorActionPreference = ''Stop'';' + #13#10 +
    '$Log = ' + PSQuote(LogPath) + ';' + #13#10 +
    '$TmpLog = Join-Path $env:TEMP ("installer_' + ScriptNameHint + '_log.txt");' + #13#10 +
    'function Write-Log($s){' + #13#10 +
    '  try { Add-Content -LiteralPath $Log -Value $s } catch { try { Add-Content -LiteralPath $TmpLog -Value $s } catch {} }' + #13#10 +
    '}' + #13#10 +
    'try {' + #13#10 +
    '  Write-Log ''CMD: ' + EscapedCmd + ''';' + #13#10 +
    '  ' + Cmd + #13#10 +
    '  Write-Log ''OK'';' + #13#10 +
    '} catch {' + #13#10 +
    '  Write-Log (''ERROR: '' + $_.Exception.Message);' + #13#10 +
    '  if ($_.InvocationInfo -ne $null) { Write-Log (''AT: '' + $_.InvocationInfo.PositionMessage) }' + #13#10 +
    '  exit 1' + #13#10 +
    '}';

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
    Exit;
  end;

  Result := True;
end;

function DownloadAndVerify(const UrlZip, UrlSha, DestZip, DestSha, LogPath: String): Boolean;
var
  Cmd: String;
begin
  Cmd :=
    '$ErrorActionPreference = ''Stop''; ' +
    '[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; ' +
    'Invoke-WebRequest -Uri ' + PSQuote(UrlZip) + ' -OutFile ' + PSQuote(DestZip) + '; ' +
    'Invoke-WebRequest -Uri ' + PSQuote(UrlSha) + ' -OutFile ' + PSQuote(DestSha) + '; ' +
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
  { 1) 앱 프로세스 종료 (잠긴 DLL 해제)
    2) Zip 임시해제 → 대상 폴더로 복사(robocopy 우선, 실패 시 폴백)
    3) 재시도 로직 및 경로 길이/읽기전용 속성 대응
    4) 최종 EXE 존재 확인/이동 }
  Cmd :=
    '$ErrorActionPreference = ''Stop''; ' +
    '$zip = ' + PSQuote(ZipPath) + '; ' +
    '$target = ' + PSQuote(TargetDir) + '; ' +
    '$temp = Join-Path $env:TEMP (''payload_'' + [guid]::NewGuid().ToString()); ' +

    'function Write-Log($s){ try{ Add-Content -LiteralPath ' + PSQuote(LogPath) + ' -Value $s } catch{} } ' +

    'New-Item -ItemType Directory -Path $temp | Out-Null; ' +
    'Add-Type -AssemblyName System.IO.Compression.FileSystem; ' +
    '[System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $temp); ' +
    '$srcCount = (Get-ChildItem -LiteralPath $temp -Recurse -Force | Where-Object { -not $_.PSIsContainer }).Count; ' +
    'if ($srcCount -eq 0) { throw (''ZIP is empty after extract: '' + $zip) } ' +

    '{ ' +
    '  # 1) 실행 중인 앱 종료(잠금 해제). 이름은 필요 시 추가. ' +
    '  $procs = @("BranchingNovelGUI","BranchingNovelEditor"); ' +
    '  foreach($n in $procs){ ' +
    '    try{ Get-Process -Name $n -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue }catch{} ' +
    '  } ' +
    '  Start-Sleep -Milliseconds 400 ' +
    '} ' +

    'if (-not (Test-Path -LiteralPath $target)) { New-Item -ItemType Directory -Path $target | Out-Null }; ' +

    '{ ' +
    '  # 2) 대상 폴더 읽기전용 속성 제거 (복사 방해 요소 제거) ' +
    '  try{ attrib -R (Join-Path $target "*") /S }catch{} ' +
    '} ' +

    'function Add-LongPrefix([string]$p){ if($p -like "\\\\?\\*"){ return $p } else { return ("\\\\?\\" + $p) } } ' +
    '$tempLP = Add-LongPrefix($temp); $targetLP = Add-LongPrefix($target); ' +

    '$robocopyPath = Join-Path $env:WINDIR "System32\\robocopy.exe"; ' +
    'if (-not (Test-Path -LiteralPath $robocopyPath)) { $robocopyPath = "robocopy.exe" } ' +
    '$robolog = Join-Path $env:TEMP (''robocopy_'' + [guid]::NewGuid().ToString() + ''.log''); ' +
    '$args = @($tempLP, $targetLP, "/E","/R:2","/W:1","/NFL","/NDL","/NP","/NJH","/NJS","/COPY:DAT","/MIR","/LOG:" + $robolog); ' +

    'function Try-Robocopy{ ' +
    '  param([int]$attempts) ' +
    '  for($i=1; $i -le $attempts; $i++){ ' +
    '    $p = Start-Process -FilePath $robocopyPath -ArgumentList $args -NoNewWindow -PassThru -Wait; ' +
    '    $code = $p.ExitCode; ' +
    '    if($code -lt 8){ return $true } ' +
    '    Write-Log ("ROBOCOPY EXIT CODE: " + $code + " (attempt " + $i + ")"); ' +
    '    try{ $tail = Get-Content -LiteralPath $robolog -Tail 80 -Encoding UTF8 -ErrorAction SilentlyContinue; foreach($line in $tail){ Write-Log("ROBOCOPY: " + $line) } }catch{} ' +
    '    Start-Sleep -Milliseconds (300 * $i) ' +
    '  } ' +
    '  return $false ' +
    '} ' +

    'if(-not (Try-Robocopy -attempts 3)){ ' +
    '  Write-Log("FALLBACK: per-file Copy-Item with retries"); ' +
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

    '$expectedExe = Join-Path $target ' + PSQuote('{#MyAppExe}') + '; ' +
    'if (-not (Test-Path -LiteralPath $expectedExe)) { ' +
    '  $found = Get-ChildItem -Path $target -Filter ' + PSQuote('{#MyAppExe}') + ' -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1; ' +
    '  if ($null -ne $found) { Move-Item -LiteralPath $found.FullName -Destination $expectedExe -Force } ' +
    '} ' +
    'if (-not (Test-Path -LiteralPath $expectedExe)) { throw ("Expected exe not found: " + $expectedExe + ". Check ZIP root & structure.") }';

  Result := WriteAndRunPS(Cmd, LogPath, 'expand_zip');
end;

{ SINGLE CurStepChanged: merge install-phase work and language-file writing }
procedure CurStepChanged(CurStep: TSetupStep);
var
  ZipPath, ShaPath, LogPath: String;
  Ok: Boolean;
  Lang, Base: String;
begin
  if CurStep = ssInstall then
  begin
    LogPath := ExpandConstant('{app}\install.log');

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

    Ok := DownloadAndVerify('{#PayloadZipURL}', '{#PayloadShaURL}', ZipPath, ShaPath, LogPath);
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
    if ActiveLanguage = 'korean' then
      Lang := 'ko'
    else
      Lang := 'en';

    Base := ExpandConstant('{app}\');
    SaveStringToFile(Base + 'language.txt', Lang, False);
    SaveStringToFile(Base + 'editor_language.txt', Lang, False);
    SaveStringToFile(Base + 'game_language.txt', Lang, False);
  end;
end;
