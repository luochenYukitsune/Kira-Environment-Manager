; Inno Setup 安装脚本 — Kira Environment Manager
; 需要 Inno Setup 6+ (https://jrsoftware.org/isdl.php)
;
; 用法:
;   1. 先运行 pyinstaller packaging.spec 生成 dist/KiraEnvManager.exe
;   2. 在 Inno Setup Compiler 中打开本文件 → Compile
;   或命令行: iscc installer.iss

#define MyAppName "Kira Environment Manager"
#define MyAppVersion "0.6.2beta"
#define MyAppPublisher "KiraAI"
#define MyAppURL "https://github.com/xxynet/KiraAI"
#define MyAppExeName "KiraEnvManager.exe"
#define MyAppAssocName "Kira Environment Manager Config"
#define MyAppAssocExt ".json"

[Setup]
; 应用信息
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; 安装目录
DefaultDirName={autopf64}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes

; 输出
OutputDir=dist\installer
OutputBaseFilename=KiraEnvManager_Setup_{#MyAppVersion}

; 图标
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; 权限和兼容性
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

; 压缩
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; 其他
CloseApplications=yes
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousGroup=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式:"

[Files]
; 主程序（单文件 exe）
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; 图标资源（运行时用于 QIcon）
Source: "app.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; 开始菜单
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
; 桌面
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; 安装完成后可选启动
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; 卸载时清理用户数据目录（可选，仅当用户确认）
Filename: "{cmd}"; Parameters: "/c rmdir /s /q ""{userappdata}\KiraEnvManager"""; Flags: runhidden; RunOnceId: "DeleteUserData"

[Code]
var
  DeleteDataPage: TInputOptionWizardPage;

procedure InitializeWizard;
begin
  { 卸载时询问是否删除用户数据 }
  DeleteDataPage := CreateInputOptionPage(
    wpSelectProgramGroup,
    '删除用户数据',
    '是否同时删除配置文件与日志？',
    '勾选后将删除 %APPDATA%\KiraEnvManager 目录（配置文件、日志、实例设置）。' + #13#10 +
    '保留此数据可在下次安装时恢复之前的配置。',
    False, False
  );
  DeleteDataPage.Add('删除配置文件与日志目录');
end;

function GetUninstallString: string;
var
  sUnInstPath: string;
  sUnInstallString: String;
begin
  sUnInstPath := ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppName")}_is1');
  sUnInstallString := '';
  if not RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString', sUnInstallString) then
    RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString);
  Result := sUnInstallString;
end;

function IsUpgrade: Boolean;
begin
  Result := (GetUninstallString <> '');
end;

function UninstallOldVersion: Integer;
var
  sUnInstallString: string;
  iResult: Integer;
begin
  sUnInstallString := GetUninstallString;
  sUnInstallString := RemoveQuotes(sUnInstallString);
  if sUninstallString <> '' then begin
    sUnInstallString := ExpandConstant('"{cmd}" /c ""') + sUnInstallString + ExpandConstant('" /VERYSILENT /NORESTART""');
    Exec('cmd.exe', '/c start /b ""' + sUnInstallString + '""', '', SW_HIDE, ewWaitUntilTerminated, iResult);
    Result := iResult;
  end else
    Result := 0;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssInstall) and IsUpgrade then
  begin
    UninstallOldVersion();
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ExecResult: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    if DeleteDataPage.CheckListBox.Checked[0] then
    begin
      { 删除 %APPDATA%\KiraEnvManager }
      Exec('cmd.exe', '/c rmdir /s /q "' + ExpandConstant('{userappdata}\KiraEnvManager') + '"',
           '', SW_HIDE, ewWaitUntilTerminated, ExecResult);
    end;
  end;
end;
