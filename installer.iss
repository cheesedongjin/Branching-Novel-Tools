; installer.iss - Online Bootstrap Installer (공용)

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
  StringChange(R, '''', '''''');
  Result := R;
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
    '$Log = ' + AddQuotes(LogPath) + ';' + #13#10 +
    'try {' + #13#10 +
    '  Add-Content -LiteralPath $Log -Value ''CMD: ' + EscapedCmd + ''';' + #13#10 +
    '  ' + Cmd + #13#10 +
    '  Add-Content -LiteralPath $Log -Value ''OK'';' + #13#10 +
    '} catch {' + #13#10 +
    '  try { Add-Content -LiteralPath $Log -Value (''ERROR: '' + $_.Exception.Message) } catch {}' + #13#10 +
    '  if ($_.InvocationInfo -ne $null) {' + #13#10 +
    '    try { Add-Content -LiteralPath $Log -Value (''AT: '' + $_.InvocationInfo.PositionMessage) } catch {}' + #13#10 +
    '  }' + #13#10 +
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
    'Invoke-WebRequest -Uri ' + AddQuotes(UrlZip) + ' -OutFile ' + AddQuotes(DestZip) + '; ' +
    'Invoke-WebRequest -Uri ' + AddQuotes(UrlSha) + ' -OutFile ' + AddQuotes(DestSha) + '; ' +
    '$expected = (Get-Content -LiteralPath ' + AddQuotes(DestSha) + ' | Select-Object -First 1).Split('' '')[0]; ' +
    'if ([string]::IsNullOrWhiteSpace($expected)) { throw ''Empty SHA file'' } ' +
    '$actual = (Get-FileHash -LiteralPath ' + AddQuotes(DestZip) + ' -Algorithm SHA256).Hash.ToLower(); ' +
    'if ($expected.ToLower() -ne $actual) { throw (''Hash mismatch. Expected: '' + $expected + '', Actual: '' + $actual) }';

  Result := WriteAndRunPS(Cmd, LogPath, 'download_verify');
end;

function ExpandZipToApp(const ZipPath, TargetDir, LogPath: String): Boolean;
var
  Cmd: String;
  TempExtractDir: String;
begin
  TempExtractDir := ExpandConstant('{tmp}\extracted');
  Cmd :=
    '$ErrorActionPreference = ''Stop''; ' +
    #13#10 +
    '# Create temp extract directory' + #13#10 +
    '$TempDir = ' + AddQuotes(TempExtractDir) + '; ' +
    'if (Test-Path -LiteralPath $TempDir) { Remove-Item -LiteralPath $TempDir -Recurse -Force -ErrorAction SilentlyContinue }; ' +
    'New-Item -ItemType Directory -Path $TempDir -Force | Out-Null; ' +
    #13#10 +
    '# Extract ZIP to temp directory' + #13#10 +
    'try {' + #13#10 +
    '  Expand-Archive -LiteralPath ' + AddQuotes(ZipPath) + ' -DestinationPath $TempDir -Force; ' +
    '} catch {' + #13#10 +
    '  Add-Type -AssemblyName System.IO.Compression.FileSystem; ' +
    '  [System.IO.Compression.ZipFile]::ExtractToDirectory(' + AddQuotes(ZipPath) + ', $TempDir); ' +
    '}; ' +
    #13#10 +
    '# Create target directory if not exists' + #13#10 +
    'if (-not (Test-Path -LiteralPath ' + AddQuotes(TargetDir) + ')) { New-Item -ItemType Directory -Path ' + AddQuotes(TargetDir) + ' -Force | Out-Null }; ' +
    #13#10 +
    '# Copy files to target using robocopy' + #13#10 +
    '$RoboArgs = @(''' + TempExtractDir + ''', ''' + TargetDir + ''', ''/MIR'', ''/R:3'', ''/W:5''); ' +
    '$Proc = Start-Process -FilePath ''robocopy'' -ArgumentList $RoboArgs -NoNewWindow -PassThru -Wait; ' +
    '# robocopy exit codes 0-7 are success or minor issues (e.g., skipped files)' + #13#10 +
    'if ($Proc.ExitCode -gt 7) { throw (''robocopy failed with exit code '' + $Proc.ExitCode) }; ' +
    #13#10 +
    '# Clean up temp directory' + #13#10 +
    'Remove-Item -LiteralPath $TempDir -Recurse -Force -ErrorAction SilentlyContinue;';

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

    WizardForm.StatusLabel.Caption := '압축 해제 및 파일 복사 중...';
    Ok := ExpandZipToApp(ZipPath, ExpandConstant('{app}'), LogPath);
    WizardForm.ProgressGauge.Style := npbstNormal;

    if not Ok then
    begin
      MsgBox('압축 해제 또는 파일 복사 실패. install.log를 확인하세요.', mbError, MB_OK);
      WizardForm.Close;
      Exit;
    end;

    SafeAddToLog(LogPath, 'END OK');
  end;
end;
