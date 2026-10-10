; Inno Setup script for the mdConverter Windows installer.
;
; Build the app first (pyinstaller mdConverter.spec), then compile:
;   ISCC.exe /DAppVersion=1.0.1 installer\mdConverter.iss
; build.bat does both. Output: dist\mdConverter-Setup-<version>.exe
;
; Requires Inno Setup 6.6 or newer (for the dynamic light/dark Windows 11 style).

#if Ver < EncodeVer(6, 6, 0)
  #error Inno Setup 6.6 or newer is required to compile this script.
#endif

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

; Folder containing the PyInstaller one-folder build (override with /DSourceDir=...).
#ifndef SourceDir
  #define SourceDir "..\dist\mdConverter"
#endif

#define AppName "mdConverter"
#define AppExeName "mdConverter.exe"
#define AppPublisher "Jordan Brais"
#define AppURL "https://github.com/jordanbrais1-hub/mdConverter"

[Setup]
; AppId identifies the app for upgrades and uninstall. Never change it.
AppId={{B2CCEAE9-BD83-4333-AC73-853F47C16264}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}

; Per-user install, no administrator prompt. Admins can still install for all
; users from the command line with /ALLUSERS.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableWelcomePage=no
DisableProgramGroupPage=yes
DisableDirPage=auto
DisableReadyPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

; Look and feel: Windows 11 style that follows the system light/dark theme.
WizardStyle=modern dynamic windows11
WizardSizePercent=100
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
WizardImageFile=..\assets\installer\wizard-100.png,..\assets\installer\wizard-125.png,..\assets\installer\wizard-150.png,..\assets\installer\wizard-175.png,..\assets\installer\wizard-200.png,..\assets\installer\wizard-250.png
WizardImageFileDynamicDark=..\assets\installer\wizard-100.png,..\assets\installer\wizard-125.png,..\assets\installer\wizard-150.png,..\assets\installer\wizard-175.png,..\assets\installer\wizard-200.png,..\assets\installer\wizard-250.png
WizardSmallImageFile=..\assets\installer\small-100.png,..\assets\installer\small-125.png,..\assets\installer\small-150.png,..\assets\installer\small-175.png,..\assets\installer\small-200.png,..\assets\installer\small-250.png
WizardSmallImageFileDynamicDark=..\assets\installer\small-100.png,..\assets\installer\small-125.png,..\assets\installer\small-150.png,..\assets\installer\small-175.png,..\assets\installer\small-200.png,..\assets\installer\small-250.png
WizardImageStretch=no

; Upgrades: close a running copy and reuse the previous install folder.
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes

OutputDir=..\dist
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Remove the previous version's bundled libraries so stale files never linger.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
