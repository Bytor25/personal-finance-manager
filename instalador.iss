; Instalador de Finanzas (Inno Setup 6).
; Lo genera construir.bat; a mano: ISCC.exe /DMyAppVersion=0.1.0 instalador.iss
; Resultado: instalador\Finanzas-Setup-<version>.exe

#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

#define MyAppName "Finanzas"
#define MyAppExe "Finanzas.exe"

[Setup]
; No cambiar AppId: así Windows reconoce las actualizaciones como el mismo programa.
AppId={{532C313E-7831-4407-9560-028CAC54977D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Finanzas personales
; Instala solo para el usuario actual: no pide permisos de administrador.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=instalador
OutputBaseFilename=Finanzas-Setup-{#MyAppVersion}
SetupIconFile=assets\finanzas.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Si la app está abierta durante una actualización, ofrece cerrarla.
CloseApplications=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "dist\Finanzas\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Borra restos de la versión anterior antes de copiar la nueva.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Comment: "Finanzas personales"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: escritorio

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Abrir Finanzas"; Flags: nowait postinstall skipifsilent

; Los datos del usuario (Documentos\Finanzas) no se tocan al desinstalar.
