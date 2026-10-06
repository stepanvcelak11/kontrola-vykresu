; Instalátor Kontroly výkresu (Inno Setup 6): KontrolaVykresu-instalace.exe
; Sestavení:  iscc /DVerze=1.0.0.123 instalace.iss   (po  pyinstaller kontrola_vykresu.spec)
;
; Instaluje se jen pro aktuálního uživatele do %LOCALAPPDATA%\Programs – nepotřebuje práva správce.
; Nainstalovaný program už Windows při spuštění neblokuje (SmartScreen se ozve nanejvýš jednou u
; staženého instalátoru) a aktualizace z programu proběhne sama na pozadí.

#ifndef Verze
  #define Verze "1.0.0.0"
#endif

[Setup]
AppId={{48E541E7-007D-4D52-B2A6-3B789DF68CFF}
AppName=Kontrola výkresu
AppVersion={#Verze}
AppVerName=Kontrola výkresu {#Verze}
AppPublisher=Kontrola výkresu
AppPublisherURL=https://github.com/stepanvcelak11/kontrola-vykresu
VersionInfoVersion={#Verze}
VersionInfoDescription=Instalace programu Kontrola výkresu
DefaultDirName={localappdata}\Programs\KontrolaVykresu
DefaultGroupName=Kontrola výkresu
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=KontrolaVykresu-instalace
SetupIconFile=kontrola\resources\ikona.ico
UninstallDisplayIcon={app}\KontrolaVykresu.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "cs"; MessagesFile: "compiler:Languages\Czech.isl"

[Tasks]
Name: "plocha"; Description: "Zástupce na ploše"; GroupDescription: "Zástupci:"

[InstallDelete]
; stará verze knihoven se nesmí míchat s novou
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\KontrolaVykresu\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Kontrola výkresu"; Filename: "{app}\KontrolaVykresu.exe"
Name: "{group}\Odinstalovat Kontrolu výkresu"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Kontrola výkresu"; Filename: "{app}\KontrolaVykresu.exe"; Tasks: plocha

[Run]
; při ruční instalaci zaškrtávátko „Spustit“, při tiché aktualizaci z programu se spustí rovnou
Filename: "{app}\KontrolaVykresu.exe"; Description: "Spustit Kontrolu výkresu"; Flags: nowait postinstall
