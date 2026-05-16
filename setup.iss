#define MyAppName "WorkTre"
#define AppVersion "2.2.3"
#define AppVersionExtended "2.2.3.0" ; Added for Windows strict VersionInfo format

[Setup]
AppName={#MyAppName}
AppVersion={#AppVersion}
AppID={#MyAppName}App
AppPublisher=Bioncos Global - IT Solutions
AppPublisherURL=https://personalcompany.example.com
AppSupportURL=https://personalcompany.example.com/support
AppUpdatesURL=https://personalcompany.example.com/updates

; Make it a true per-user install (No Admin prompt needed)
PrivilegesRequired=lowest
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}

OutputBaseFilename={#MyAppName}Setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
DisableProgramGroupPage=yes

UninstallDisplayIcon={app}\WorkTre.exe
SetupIconFile=dist\WorkTre\setup.ico

; Version info for the installer executable
VersionInfoVersion={#AppVersionExtended}
VersionInfoCompany=Bioncos Global - IT Solutions
VersionInfoDescription=WorkTre Desktop Application
VersionInfoCopyright=Copyright © 2026 Bioncos Global
VersionInfoProductName=WorkTre
VersionInfoProductVersion={#AppVersionExtended}
VersionInfoProductTextVersion={#AppVersion}

[Files]
; This single line copies the executable, version.txt, icon.ico, and all other assets
Source: "dist\WorkTre\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\WorkTre.exe"; IconFilename: "{app}\icon.ico"
; Changed commondesktop to autodesktop to match the localappdata installation
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\WorkTre.exe"; IconFilename: "{app}\icon.ico"

[InstallDelete]
; Clean up potential duplicate shortcuts from older installers (all-users vs per-user desktop)
Type: files; Name: "{commondesktop}\{#MyAppName}.lnk"
Type: files; Name: "{autodesktop}\{#MyAppName}.lnk"

[Run]
Filename: "{app}\WorkTre.exe"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Registry]
; ✅ Auto-start on boot
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\WorkTre.exe"""; Flags: uninsdeletevalue

; ✅ Set Publisher manually for Control Panel display (fallback for old Inno Setup)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}App_is1"; \
    ValueType: string; ValueName: "Publisher"; ValueData: "WorkTre"; Flags: uninsdeletevalue

[Code]
function ExtractExeFromCommand(const Command: String): String;
var
  S: String;
  P: Integer;
begin
  S := Trim(Command);
  if S = '' then
  begin
    Result := '';
    exit;
  end;

  if Copy(S, 1, 1) = '"' then
  begin
    Delete(S, 1, 1);
    P := Pos('"', S);
    if P > 0 then
      Result := Copy(S, 1, P - 1)
    else
      Result := S;
    exit;
  end;

  P := Pos(' ', S);
  if P > 0 then
    Result := Copy(S, 1, P - 1)
  else
    Result := S;
end;

function TryGetUninstallCommandFromKey(const RootKey: Integer; const SubKey: String; var UninstallCmd: String): Boolean;
begin
  UninstallCmd := '';
  Result :=
    RegQueryStringValue(RootKey, SubKey, 'QuietUninstallString', UninstallCmd) or
    RegQueryStringValue(RootKey, SubKey, 'UninstallString', UninstallCmd);
end;

function FindWorkTreUninstallCommand(var UninstallCmd: String): Boolean;
var
  UninstallRoot: String;
  Keys: TArrayOfString;
  I: Integer;
  DisplayName: String;
  SubKey: String;
begin
  UninstallCmd := '';
  UninstallRoot := 'Software\Microsoft\Windows\CurrentVersion\Uninstall';

  // First, try the "current" AppId key (covers same-App upgrades)
  if TryGetUninstallCommandFromKey(HKCU, UninstallRoot + '\{#MyAppName}App_is1', UninstallCmd) then
  begin
    Result := True;
    exit;
  end;
  if TryGetUninstallCommandFromKey(HKLM, UninstallRoot + '\{#MyAppName}App_is1', UninstallCmd) then
  begin
    Result := True;
    exit;
  end;
  if TryGetUninstallCommandFromKey(HKLM32, UninstallRoot + '\{#MyAppName}App_is1', UninstallCmd) then
  begin
    Result := True;
    exit;
  end;

  // Fallback: search uninstall entries by DisplayName so we still upgrade even if AppId changed previously
  if RegGetSubkeyNames(HKCU, UninstallRoot, Keys) then
  begin
    for I := 0 to GetArrayLength(Keys) - 1 do
    begin
      SubKey := UninstallRoot + '\' + Keys[I];
      if RegQueryStringValue(HKCU, SubKey, 'DisplayName', DisplayName) and (DisplayName = '{#MyAppName}') then
        if TryGetUninstallCommandFromKey(HKCU, SubKey, UninstallCmd) then
        begin
          Result := True;
          exit;
        end;
    end;
  end;

  if RegGetSubkeyNames(HKLM, UninstallRoot, Keys) then
  begin
    for I := 0 to GetArrayLength(Keys) - 1 do
    begin
      SubKey := UninstallRoot + '\' + Keys[I];
      if RegQueryStringValue(HKLM, SubKey, 'DisplayName', DisplayName) and (DisplayName = '{#MyAppName}') then
        if TryGetUninstallCommandFromKey(HKLM, SubKey, UninstallCmd) then
        begin
          Result := True;
          exit;
        end;
    end;
  end;

  if RegGetSubkeyNames(HKLM32, UninstallRoot, Keys) then
  begin
    for I := 0 to GetArrayLength(Keys) - 1 do
    begin
      SubKey := UninstallRoot + '\' + Keys[I];
      if RegQueryStringValue(HKLM32, SubKey, 'DisplayName', DisplayName) and (DisplayName = '{#MyAppName}') then
        if TryGetUninstallCommandFromKey(HKLM32, SubKey, UninstallCmd) then
        begin
          Result := True;
          exit;
        end;
    end;
  end;

  Result := False;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  UninstallCmd: String;
  UninstallExe: String;
  iResultCode: Integer;
begin
  if FindWorkTreUninstallCommand(UninstallCmd) then
  begin
    UninstallExe := ExtractExeFromCommand(UninstallCmd);

    if (UninstallExe <> '') and FileExists(UninstallExe) then
    begin
      // Use runas so we can remove both per-user and machine-wide installs reliably.
      // If elevation isn't needed, Windows will simply run it normally.
      if MsgBox('A previous installation of {#MyAppName} was detected. It will be uninstalled before installing version {#AppVersion}.' + #13#10 + #13#10 + 'Do you want to continue?', mbConfirmation, MB_YESNO) = IDYES then
      begin
        if ShellExec('runas', UninstallExe, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_SHOW, ewWaitUntilTerminated, iResultCode) then
          Result := ''
        else
          Result := 'Failed to uninstall the previous version. Please uninstall it manually from the Control Panel and rerun this installer.';
      end
      else
        Result := 'Installation cancelled by the user.';
    end;
  end;
end;

procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel2.Caption := 'Installer created by WorkTre';
end;
