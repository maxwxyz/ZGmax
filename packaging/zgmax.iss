; Installer fuer Windows (Inno Setup 6). Baut aus dem fertigen Ordner dist\ZGmax eine Setup-Datei:
;   ISCC /DAPPVER=1.0 packaging\zgmax.iss      ->  dist\ZGmax-1.0-Windows-x64-Setup.exe
; Ohne Adminrechte installierbar: der Installer fragt "fuer alle" oder "nur fuer mich"; ohne Adminrechte geht es
; automatisch nur fuer den angemeldeten Nutzer (%LocalAppData%\Programs\ZGmax). Dateitypen sind waehlbar; die
; Eintraege entsprechen programm\fileassoc.py (ZGmax.Zeichnung / ZGmax.Projekt), nur je nach Installationsart
; fuer alle (HKLM) oder den Nutzer (HKCU) - HKA waehlt das selbst.
; Update: dieselbe AppId -> eine neuere, gleiche oder aeltere Version installiert sich ueber die vorhandene (gleicher
; Ordner, gleiche Art fuer alle/nur Nutzer). Alte Programmdateien (_internal) werden vorher entfernt, damit nichts
; aus einer frueheren Version liegen bleibt; Einstellungen und Projekte des Nutzers liegen woanders und bleiben.
; Die portable App (ZIP mit ZGmax.exe und _internal) bleibt daneben bestehen.
#ifndef APPVER
  #define APPVER "0.0"
#endif
#define APP "ZGmax"
#define EXE "ZGmax.exe"

[Setup]
AppId={{6F1B6A0E-5C0B-4B7E-9C55-2A7D4E0F9A31}
AppName={#APP}
AppVersion={#APPVER}
AppVerName={#APP} {#APPVER}
AppPublisher=Max Wilfinger
DefaultDirName={autopf}\{#APP}
DefaultGroupName={#APP}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename={#APP}-{#APPVER}-Windows-x64-Setup
SetupIconFile=..\programm\icon.ico
UninstallDisplayIcon={app}\{#EXE}
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
CloseApplications=yes
UsePreviousAppDir=yes
UsePreviousPrivileges=yes
UsePreviousTasks=yes

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
de.Types=Dateitypen, die sich mit ZGmax öffnen lassen ("Öffnen mit"):
en.Types=File types that can be opened with ZGmax ("Open with"):
de.Project=ZGmax-Projekte (.zgmax) mit ZGmax öffnen
en.Project=Open ZGmax projects (.zgmax) with ZGmax
de.Desktop=Symbol auf dem Desktop
en.Desktop=Desktop icon
de.Drawing=Zeichnung (ZGmax)
en.Drawing=Drawing (ZGmax)
de.ProjectName=ZGmax-Projekt
en.ProjectName=ZGmax project
de.Describe=Technische Zeichnungen ansehen, vergleichen und prüfen
en.Describe=View, compare and review technical drawings
de.Launch=ZGmax jetzt starten
en.Launch=Start ZGmax now

[Tasks]
Name: "desktopicon"; Description: "{cm:Desktop}"; Flags: unchecked
Name: "assoc_zgmax"; Description: "{cm:Project}"
Name: "assoc_pdf"; Description: "PDF (.pdf)"; GroupDescription: "{cm:Types}"
Name: "assoc_png"; Description: "PNG (.png)"; GroupDescription: "{cm:Types}"
Name: "assoc_jpg"; Description: "JPEG (.jpg, .jpeg)"; GroupDescription: "{cm:Types}"
Name: "assoc_tif"; Description: "TIFF (.tif, .tiff)"; GroupDescription: "{cm:Types}"
Name: "assoc_bmp"; Description: "BMP (.bmp)"; GroupDescription: "{cm:Types}"
Name: "assoc_webp"; Description: "WebP (.webp)"; GroupDescription: "{cm:Types}"
Name: "assoc_svg"; Description: "SVG (.svg)"; GroupDescription: "{cm:Types}"
Name: "assoc_dxf"; Description: "DXF (.dxf)"; GroupDescription: "{cm:Types}"

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\ZGmax\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#APP}"; Filename: "{app}\{#EXE}"
Name: "{autodesktop}\{#APP}"; Filename: "{app}\{#EXE}"; Tasks: desktopicon

[Registry]
; Programmkennungen (wie fileassoc.py)
Root: HKA; Subkey: "Software\Classes\ZGmax.Zeichnung"; ValueType: string; ValueData: "{cm:Drawing}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\ZGmax.Zeichnung\DefaultIcon"; ValueType: string; ValueData: """{app}\{#EXE}"",0"
Root: HKA; Subkey: "Software\Classes\ZGmax.Zeichnung\shell\open\command"; ValueType: string; ValueData: """{app}\{#EXE}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\ZGmax.Projekt"; ValueType: string; ValueData: "{cm:ProjectName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\ZGmax.Projekt\DefaultIcon"; ValueType: string; ValueData: """{app}\{#EXE}"",0"
Root: HKA; Subkey: "Software\Classes\ZGmax.Projekt\shell\open\command"; ValueType: string; ValueData: """{app}\{#EXE}"" ""%1"""
; damit ZGmax in den Windows-Einstellungen unter "Standard-Apps" mit seinen Typen erscheint
Root: HKA; Subkey: "Software\ZGmax\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#APP}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\ZGmax\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "{cm:Describe}"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#APP}"; ValueData: "Software\ZGmax\Capabilities"; Flags: uninsdeletevalue
; eigener Typ: direkt Standard
Root: HKA; Subkey: "Software\Classes\.zgmax"; ValueType: string; ValueData: "ZGmax.Projekt"; Flags: uninsdeletevalue; Tasks: assoc_zgmax
Root: HKA; Subkey: "Software\Classes\.zgmax\OpenWithProgids"; ValueType: none; ValueName: "ZGmax.Projekt"; Flags: uninsdeletevalue; Tasks: assoc_zgmax
Root: HKA; Subkey: "Software\ZGmax\Capabilities\FileAssociations"; ValueType: string; ValueName: ".zgmax"; ValueData: "ZGmax.Projekt"; Tasks: assoc_zgmax
; fremde Typen: ZGmax bei "Oeffnen mit" anbieten (den Standard setzt seit Windows 10 nur der Nutzer selbst)
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: none; ValueName: "ZGmax.Zeichnung"; Flags: uninsdeletevalue; Tasks: assoc_pdf
Root: HKA; Subkey: "Software\ZGmax\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "ZGmax.Zeichnung"; Tasks: assoc_pdf
Root: HKA; Subkey: "Software\Classes\.png\OpenWithProgids"; ValueType: none; ValueName: "ZGmax.Zeichnung"; Flags: uninsdeletevalue; Tasks: assoc_png
Root: HKA; Subkey: "Software\ZGmax\Capabilities\FileAssociations"; ValueType: string; ValueName: ".png"; ValueData: "ZGmax.Zeichnung"; Tasks: assoc_png
Root: HKA; Subkey: "Software\Classes\.jpg\OpenWithProgids"; ValueType: none; ValueName: "ZGmax.Zeichnung"; Flags: uninsdeletevalue; Tasks: assoc_jpg
Root: HKA; Subkey: "Software\ZGmax\Capabilities\FileAssociations"; ValueType: string; ValueName: ".jpg"; ValueData: "ZGmax.Zeichnung"; Tasks: assoc_jpg
Root: HKA; Subkey: "Software\Classes\.jpeg\OpenWithProgids"; ValueType: none; ValueName: "ZGmax.Zeichnung"; Flags: uninsdeletevalue; Tasks: assoc_jpg
Root: HKA; Subkey: "Software\ZGmax\Capabilities\FileAssociations"; ValueType: string; ValueName: ".jpeg"; ValueData: "ZGmax.Zeichnung"; Tasks: assoc_jpg
Root: HKA; Subkey: "Software\Classes\.tif\OpenWithProgids"; ValueType: none; ValueName: "ZGmax.Zeichnung"; Flags: uninsdeletevalue; Tasks: assoc_tif
Root: HKA; Subkey: "Software\ZGmax\Capabilities\FileAssociations"; ValueType: string; ValueName: ".tif"; ValueData: "ZGmax.Zeichnung"; Tasks: assoc_tif
Root: HKA; Subkey: "Software\Classes\.tiff\OpenWithProgids"; ValueType: none; ValueName: "ZGmax.Zeichnung"; Flags: uninsdeletevalue; Tasks: assoc_tif
Root: HKA; Subkey: "Software\ZGmax\Capabilities\FileAssociations"; ValueType: string; ValueName: ".tiff"; ValueData: "ZGmax.Zeichnung"; Tasks: assoc_tif
Root: HKA; Subkey: "Software\Classes\.bmp\OpenWithProgids"; ValueType: none; ValueName: "ZGmax.Zeichnung"; Flags: uninsdeletevalue; Tasks: assoc_bmp
Root: HKA; Subkey: "Software\ZGmax\Capabilities\FileAssociations"; ValueType: string; ValueName: ".bmp"; ValueData: "ZGmax.Zeichnung"; Tasks: assoc_bmp
Root: HKA; Subkey: "Software\Classes\.webp\OpenWithProgids"; ValueType: none; ValueName: "ZGmax.Zeichnung"; Flags: uninsdeletevalue; Tasks: assoc_webp
Root: HKA; Subkey: "Software\ZGmax\Capabilities\FileAssociations"; ValueType: string; ValueName: ".webp"; ValueData: "ZGmax.Zeichnung"; Tasks: assoc_webp
Root: HKA; Subkey: "Software\Classes\.svg\OpenWithProgids"; ValueType: none; ValueName: "ZGmax.Zeichnung"; Flags: uninsdeletevalue; Tasks: assoc_svg
Root: HKA; Subkey: "Software\ZGmax\Capabilities\FileAssociations"; ValueType: string; ValueName: ".svg"; ValueData: "ZGmax.Zeichnung"; Tasks: assoc_svg
Root: HKA; Subkey: "Software\Classes\.dxf\OpenWithProgids"; ValueType: none; ValueName: "ZGmax.Zeichnung"; Flags: uninsdeletevalue; Tasks: assoc_dxf
Root: HKA; Subkey: "Software\ZGmax\Capabilities\FileAssociations"; ValueType: string; ValueName: ".dxf"; ValueData: "ZGmax.Zeichnung"; Tasks: assoc_dxf

[Run]
Filename: "{app}\{#EXE}"; Description: "{cm:Launch}"; Flags: nowait postinstall skipifsilent
