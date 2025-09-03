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
AppId={{B1C50C47-7B73-4308-9C74-2A9B3E11A9D3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
Compression=lzma2
SolidCompression=yes
OutputBaseFilename={#MyAppName}-Online-Setup
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExe}
SetupLogging=yes
SetupIconFile=assets\icons\app.ico

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "추가 작업:"; Flags: unchecked

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\프로그램 제거"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{#MyAppName} 실행"; Flags: nowait postinstall skipifsilent

[Registry]
; .bnov 확장자를 {#MyAppExe}에 연결
Root: HKCR; Subkey: ".bnov"; ValueType: string; ValueName: ""; ValueData: "BranchingNovelFile"; Flags: uninsdeletevalue
Root: HKCR; Subkey: "BranchingNovelFile"; ValueType: string; ValueName: ""; ValueData: "Branching Novel Script"; Flags: uninsdeletekey
Root: HKCR; Subkey: "BranchingNovelFile\DefaultIcon"; ValueType: string; ValueData: "{app}\{#MyAppExe},0"
Root: HKCR; Subkey: "BranchingNovelFile\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""

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

{ PowerShell에서 사용할 문자열 인용: 항상 단일따옴표로 감싸고 내부 ' 이스케이프 }
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
  { 1) 임시 폴더에 해제(.NET ZipFile)
    2) 소스 파일 개수 검증
    3) 대상 폴더 생성
    4) robocopy 정식 경로 호출 + 인자 배열
    5) 실패 시 robocopy 로그 꼬리를 install.log에 기록
    6) robocopy 실패하면 Copy-Item -Path 로 폴백 복사(와일드카드 확장)
    7) 루트에 EXE 없으면 재배치(하위에서 찾아 루트로 이동)
    8) 최종 EXE 존재 검증 }
  Cmd :=
    '$ErrorActionPreference = ''Stop''; ' +
    '$zip = ' + PSQuote(ZipPath) + '; ' +
    '$target = ' + PSQuote(TargetDir) + '; ' +
    '$temp = Join-Path $env:TEMP (''payload_'' + [guid]::NewGuid().ToString()); ' +
    'New-Item -ItemType Directory -Path $temp | Out-Null; ' +
    'Add-Type -AssemblyName System.IO.Compression.FileSystem; ' +
    '[System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $temp); ' +
    '$srcCount = (Get-ChildItem -LiteralPath $temp -Recurse -Force | Where-Object { -not $_.PSIsContainer }).Count; ' +
    'if ($srcCount -eq 0) { throw (''ZIP is empty after extract: '' + $zip) } ' +
    'if (-not (Test-Path -LiteralPath $target)) { New-Item -ItemType Directory -Path $target | Out-Null }; ' +

    '$robocopyPath = Join-Path $env:WINDIR "System32\\robocopy.exe"; ' +
    'if (-not (Test-Path -LiteralPath $robocopyPath)) { $robocopyPath = "robocopy.exe" } ' +
    '$robolog = Join-Path $env:TEMP (''robocopy_'' + [guid]::NewGuid().ToString() + ''.log''); ' +
    '$args = @($temp, $target, "/E","/R:1","/W:1","/NFL","/NDL","/NP","/NJH","/NJS","/COPY:DAT", "/LOG:" + $robolog); ' +
    '$p = Start-Process -FilePath $robocopyPath -ArgumentList $args -NoNewWindow -PassThru -Wait; ' +
    '$code = $p.ExitCode; ' +
    'if ($code -ge 8) { ' +
    '  try { $tail = Get-Content -LiteralPath $robolog -Tail 80 -ErrorAction SilentlyContinue -Encoding UTF8; foreach ($line in $tail) { Write-Log("ROBOCOPY: " + $line) } } catch {} ' +
    '  Write-Log("ROBOCOPY EXIT CODE: " + $code); ' +
    '  Write-Log("ROBOCOPY LOG: " + $robolog); ' +
    '  Write-Log("FALLBACK: Copy-Item -Recurse -Force (with wildcard expansion)"); ' +
    '  Copy-Item -Path (Join-Path $temp ''*'') -Destination $target -Recurse -Force -ErrorAction Stop; ' +
    '} ' +

    { 루트에 EXE가 없으면 하위에서 찾아 루트로 이동 }
    '$expectedExe = Join-Path $target ' + PSQuote('{#MyAppExe}') + '; ' +
    'if (-not (Test-Path -LiteralPath $expectedExe)) { ' +
    '  $found = Get-ChildItem -Path $target -Filter ' + PSQuote('{#MyAppExe}') + ' -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1; ' +
    '  if ($null -ne $found) { ' +
    '    Move-Item -LiteralPath $found.FullName -Destination $expectedExe -Force; ' +
    '  } ' +
    '} ' +

    'if (-not (Test-Path -LiteralPath $expectedExe)) { ' +
    '  throw ("Expected exe not found: " + $expectedExe + ". Check ZIP root & folder structure.") ' +
    '}';

  Result := WriteAndRunPS(Cmd, LogPath, 'expand_zip');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ZipPath, ShaPath, LogPath: String;
  Ok: Boolean;
begin
  if CurStep = ssInstall then
  begin
    LogPath := ExpandConstant('{app}\install.log');

    if not IsPSAvailable() then
    begin
      SafeAddToLog(LogPath, 'PowerShell not found');
      MsgBox('PowerShell을 찾을 수 없습니다. Windows 10/11에서 실행해 주세요.', mbError, MB_OK);
      WizardForm.Close;
      Exit;
    end;

    SafeAddToLog(LogPath, 'BEGIN INSTALL');

    ZipPath := ExpandConstant('{tmp}\payload.zip');
    ShaPath := ExpandConstant('{tmp}\payload.sha256');

    WizardForm.StatusLabel.Caption := '다운로드 및 검증 중...';
    try
      WizardForm.ProgressGauge.Style := npbstMarquee;
    except
      WizardForm.ProgressGauge.Style := npbstNormal;
    end;

    Ok := DownloadAndVerify('{#PayloadZipURL}', '{#PayloadShaURL}', ZipPath, ShaPath, LogPath);
    if not Ok then
    begin
      WizardForm.ProgressGauge.Style := npbstNormal;
      MsgBox('다운로드/무결성 검증 실패. install.log를 확인하세요.', mbError, MB_OK);
      WizardForm.Close;
      Exit;
    end;

    WizardForm.StatusLabel.Caption := '압축 해제 중...';
    Ok := ExpandZipToApp(ZipPath, ExpandConstant('{app}'), LogPath);
    WizardForm.ProgressGauge.Style := npbstNormal;

    if not Ok then
    begin
      MsgBox('압축 해제 실패. install.log를 확인하세요.', mbError, MB_OK);
      WizardForm.Close;
      Exit;
    end;

    SafeAddToLog(LogPath, 'END OK');
  end;
end;
