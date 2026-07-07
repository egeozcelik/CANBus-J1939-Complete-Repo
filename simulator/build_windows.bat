@echo off
REM ============================================================
REM  Build the single-file Windows executable for the
REM  J1939 Simulator (Tkinter desktop front-end).
REM
REM  Output:  dist\J1939-Simulator.exe   (double-click to run)
REM
REM  Requires Python 3.10+ on PATH. Everything else is installed
REM  automatically below.
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo [1/3] Installing build dependencies (python-can, pyinstaller)...
python -m pip install --disable-pip-version-check python-can pyinstaller || goto :error

echo.
echo [2/3] Packaging desktop_app.py into a single .exe...
python -m PyInstaller ^
  --noconfirm --clean --onefile --windowed ^
  --name J1939-Simulator ^
  --icon "%cd%\assets\icon.ico" ^
  --hidden-import can.interfaces.virtual ^
  --collect-submodules can ^
  --distpath dist --workpath build\pyi --specpath build ^
  desktop_app.py || goto :error

echo.
echo [3/3] Done.
echo Executable: %cd%\dist\J1939-Simulator.exe
echo Double-click it, then press START SIMULATION.
goto :eof

:error
echo.
echo BUILD FAILED. See the messages above.
exit /b 1
