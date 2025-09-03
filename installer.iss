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
; .bnov 확장자를 Branching Novel GUI에 연결
Root: HKCR; Subkey: ".bnov"; ValueType: string; ValueName: ""; ValueData: "BranchingNovelFile"; Flags: uninsdeletevalue
Root: HKCR; Subkey: "BranchingNovelFile"; ValueType: string; ValueName: ""; ValueData: "Branching Novel Script"; Flags: uninsdeletekey
Root: HKCR; Subkey: "BranchingNovelFile\DefaultIcon"; ValueType: string; ValueData: "{app}\{#MyAppExe},0"
Root: HKCR; Subkey: "BranchingNovelFile\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""

[Code]
function IsPSAvailable(): Boolean;
var ResultCode: Integer;
begin
  Result := Exec('powershell.exe', '-NoLogo -NoProfile -Command "$PSVersionTable.PSVersion.Major"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure AddToLog(const LogPath, Line: String);
begin
  SaveStringToFile(LogPath, Line + #13#10, True);
end;

function RunPSLog(const Cmd, LogPath: String): Boolean;
var
  ResultCode: Integer;
  PSArgs, FullCmd: String;
begin
  PSArgs := '-NoLogo -NoProfile -ExecutionPolicy Bypass -Command ';
  FullCmd := '$ErrorActionPreference="Stop"; ' +
             'Add-Content -Path ' + AddQuotes(LogPath) + ' -Value "CMD: ' + StringChange(Cmd, '"', '""') + '"; ' +
             Cmd + '; ' +
             'Add-Content -Path ' + AddQuotes(LogPath) + ' -Value "OK"';
  Result := Exec('powershell.exe', PSArgs + AddQuotes(FullCmd), '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if not Result then
    AddToLog(LogPath, 'PS ERROR code=' + IntToStr(ResultCode));
end;

function DownloadAndVerify(const UrlZip, UrlSha, DestZip, DestSha: String): Boolean;
var
  Cmd, LogPath: String;
begin
  LogPath := ExpandConstant('{app}\install.log');
  Cmd := '$ErrorActionPreference="Stop"; ' +
         '[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; ' +
         'Invoke-WebRequest -UseBasicParsing -Uri ' + AddQuotes(UrlZip) + ' -OutFile ' + AddQuotes(DestZip) + '; ' +
         'Invoke-WebRequest -UseBasicParsing -Uri ' + AddQuotes(UrlSha) + ' -OutFile ' + AddQuotes(DestSha) + ';';
  if not RunPSLog(Cmd, LogPath) then
  begin
    Result := False;
    exit;
  end;

  Cmd := '$ErrorActionPreference="Stop"; ' +
         '$expected = (Get-Content -Path ' + AddQuotes(DestSha) + ' | Select-Object -First 1).Split(" ",[System.StringSplitOptions]::RemoveEmptyEntries)[0]; ' +
         '$actual = (Get-FileHash -Path ' + AddQuotes(DestZip) + ' -Algorithm SHA256).Hash.ToLower(); ' +
         'if ($expected.ToLower() -ne $actual) { throw "Hash mismatch. Expected: $expected, Actual: $actual" }';
  if not RunPSLog(Cmd, LogPath) then
  begin
    Result := False;
    exit;
  end;
  Result := True;
end;

function ExpandZipToApp(const ZipPath, TargetDir: String): Boolean;
var
  Cmd, LogPath: String;
begin
  LogPath := ExpandConstant('{app}\install.log');
  Cmd := '$ErrorActionPreference="Stop"; ' +
         'if (-not (Test-Path -Path ' + AddQuotes(TargetDir) + ')) { New-Item -ItemType Directory -Path ' + AddQuotes(TargetDir) + ' | Out-Null }; ' +
         'try { Expand-Archive -LiteralPath ' + AddQuotes(ZipPath) + ' -DestinationPath ' + AddQuotes(TargetDir) + ' -Force } ' +
         'catch { Add-Type -AssemblyName System.IO.Compression.FileSystem; [System.IO.Compression.ZipFile]::ExtractToDirectory(' + AddQuotes(ZipPath) + ', ' + AddQuotes(TargetDir) + ') }';
  Result := RunPSLog(Cmd, LogPath);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ZipPath, ShaPath, LogPath: String;
  Ok: Boolean;
begin
  if CurStep = ssInstall then
  begin
    if not IsPSAvailable() then
    begin
      AddToLog(ExpandConstant('{app}\install.log'), 'PowerShell not found');
      MsgBox('PowerShell을 찾을 수 없습니다. Windows 10/11에서 실행해 주세요.', mbError, MB_OK);
      WizardForm.Close;
      exit;
    end;

    LogPath := ExpandConstant('{app}\install.log');
    AddToLog(LogPath, 'BEGIN INSTALL');
    ZipPath := ExpandConstant('{tmp}\payload.zip');
    ShaPath := ExpandConstant('{tmp}\payload.sha256');

    WizardForm.StatusLabel.Caption := '다운로드 중...';
    WizardForm.ProgressGauge.Style := npbstMarquee;

    Ok := DownloadAndVerify('{#PayloadZipURL}', '{#PayloadShaURL}', ZipPath, ShaPath);
    if not Ok then
    begin
      WizardForm.ProgressGauge.Style := npbstNormal;
      MsgBox('다운로드/무결성 검증 실패. install.log를 확인하세요.', mbError, MB_OK);
      WizardForm.Close;
      exit;
    end;

    WizardForm.StatusLabel.Caption := '압축 해제 중...';
    Ok := ExpandZipToApp(ZipPath, ExpandConstant('{app}'));
    WizardForm.ProgressGauge.Style := npbstNormal;

    if not Ok then
    begin
      MsgBox('압축 해제 실패. install.log를 확인하세요.', mbError, MB_OK);
      WizardForm.Close;
      exit;
    end;
    AddToLog(LogPath, 'END OK');
  end;
end;
