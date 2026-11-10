@echo off
rem Genera dist\Finanzas\Finanzas.exe y deja el acceso directo del menu Inicio apuntando a el.
cd /d "%~dp0"
call .venv\Scripts\activate.bat || (echo Crea el entorno: py -3.12 -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt & exit /b 1)
python -m pytest -q || exit /b 1
pyinstaller --noconfirm --clean --onedir --windowed --name Finanzas --icon assets\finanzas.ico ^
  --add-data "assets\finanzas.ico;assets" --collect-data customtkinter ^
  --collect-all flet --collect-all flet_desktop --collect-all flet_web --collect-all flet_charts ^
  --collect-all webview --collect-submodules uvicorn main.py ^
  || (echo. & echo ERROR: no se pudo generar el ejecutable. Si Finanzas.exe esta abierto, cierralo y vuelve a intentar. & exit /b 1)

rem Acceso directo en el menu Inicio (siempre apunta a la misma ruta, asi abre la version mas reciente).
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$exe = Join-Path '%~dp0' 'dist\Finanzas\Finanzas.exe';" ^
  "$lnk = Join-Path ([Environment]::GetFolderPath('Programs')) 'Finanzas.lnk';" ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk);" ^
  "$s.TargetPath = $exe; $s.WorkingDirectory = Split-Path $exe; $s.IconLocation = $exe + ',0';" ^
  "$s.Description = 'Finanzas personales'; $s.Save(); Write-Host ('Acceso directo: ' + $lnk)"

echo.
echo Listo: dist\Finanzas\Finanzas.exe

rem Instalador para compartir (requiere Inno Setup 6: winget install JRSoftware.InnoSetup).
set "ISCC="
for %%P in ("%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do if exist %%P set "ISCC=%%~P"
if not defined ISCC (echo. & echo Inno Setup no esta instalado: se omite el instalador. & exit /b 0)
for /f %%V in ('python -c "import finanzas; print(finanzas.__version__)"') do set "VERSION=%%V"
"%ISCC%" /Q /DMyAppVersion=%VERSION% instalador.iss || (echo ERROR: no se pudo generar el instalador. & exit /b 1)
echo Instalador: instalador\Finanzas-Setup-%VERSION%.exe
