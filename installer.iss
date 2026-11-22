; Inno Setup script: builds TazkiyahDownloader-Setup-<version>.exe from dist\TazkiyahDownloader
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6C1F3B7E-8A55-4F0B-9E2D-1D7A4C2B9F10}
AppName=Tazkiyah Downloader
AppVersion={#AppVersion}
AppPublisher=Tazkiyah
DefaultDirName={localappdata}\Programs\Tazkiyah Downloader
DefaultGroupName=Tazkiyah Downloader
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=TazkiyahDownloader-Setup-{#AppVersion}
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\TazkiyahDownloader.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\TazkiyahDownloader\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Tazkiyah Downloader"; Filename: "{app}\TazkiyahDownloader.exe"
Name: "{autodesktop}\Tazkiyah Downloader"; Filename: "{app}\TazkiyahDownloader.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TazkiyahDownloader.exe"; Description: "Open Tazkiyah Downloader"; Flags: nowait postinstall skipifsilent
