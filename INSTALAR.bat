@echo off
chcp 65001 >nul
setlocal
title Stage Exporter - instalador
set "HERE=%~dp0"
set "TOOL=%~1"
if not defined TOOL if exist "%HERE%..\_internal\wrcg2acr-worker.exe" set "TOOL=%HERE%.."
if not defined TOOL if exist "%HERE%_internal\wrcg2acr-worker.exe" set "TOOL=%HERE%."
if not defined TOOL (
  echo No encuentro el Stage Export Tool junto a este instalador.
  set /p "TOOL=Pega la carpeta del Stage Export Tool y pulsa Intro: "
)
set "TOOL=%TOOL:"=%"
if not exist "%TOOL%\_internal\wrcg2acr-worker.exe" (
  echo.
  echo No encuentro "_internal\wrcg2acr-worker.exe" en: %TOOL%
  echo Pon esta carpeta dentro de la del Stage Export Tool, o arrastra la carpeta de la herramienta sobre INSTALAR.bat.
  pause
  exit /b 1
)
echo Instalando en: %TOOL%
echo.
xcopy "%HERE%payload\_internal" "%TOOL%\_internal\" /E /I /Y /Q >nul || goto :fail
xcopy "%HERE%payload\custom" "%TOOL%\custom\" /E /I /Y /Q >nul || goto :fail
if exist "%HERE%payload\bin" xcopy "%HERE%payload\bin" "%TOOL%\bin\" /E /I /Y /Q >nul || goto :fail
"%TOOL%\_internal\wrcg2acr-worker.exe" -m wr_setup || goto :fail
echo.
pause
exit /b 0
:fail
echo.
echo Algo ha fallado (mira los mensajes de arriba).
pause
exit /b 1
