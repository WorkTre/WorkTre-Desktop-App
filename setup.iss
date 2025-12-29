#define MyAppName "WorkTre"
#define AppVersion "2.0.1"

[Setup]
AppName={#MyAppName}
AppVersion={#AppVersion}
AppID={#MyAppName}App
AppPublisher=Bioncos Global - IT Solutions
VersionInfoVersion={#AppVersion}
VersionInfoCompany=Bioncos Global - IT Solutions
VersionInfoDescription=WorkTre Desktop Application
VersionInfoCopyright=Copyright © 2025 Bioncos Global
VersionInfoProductName=WorkTre
VersionInfoProductVersion={#AppVersion}
VersionInfoProductTextVersion={#AppVersion}
AppPublisherURL=https://personalcompany.example.com
AppSupportURL=https://personalcompany.example.com/support
AppUpdatesURL=https://personalcompany.example.com/updates
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputBaseFilename={#MyAppName}Setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\WorkTre.exe
SetupIconFile=dist\WorkTre\setup.ico

[Files]
Source: "dist\WorkTre\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "dist\WorkTre\version.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\WorkTre\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\WorkTre.exe"; IconFilename: "{app}\icon.ico"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\WorkTre.exe"; IconFilename: "{app}\icon.ico"

[Run]
Filename: "{app}\WorkTre.exe"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Registry]
; ✅ Auto-start on boot
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\WorkTre.exe"""; Flags: uninsdeletevalue

; ✅ Set Publisher manually for Control Panel display (fallback for old Inno Setup)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_is1"; \
    ValueType: string; ValueName: "Publisher"; ValueData: "WorkTre"; Flags: uninsdeletevalue

[Code]
procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel2.Caption := 'Installer created by WorkTre';
end;
