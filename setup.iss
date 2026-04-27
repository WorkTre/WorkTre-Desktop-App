#define MyAppName "WorkTre"
#define AppVersion "2.2.2"
#define AppVersionExtended "2.2.2.0" ; Added for Windows strict VersionInfo format

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
procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel2.Caption := 'Installer created by WorkTre';
end;
