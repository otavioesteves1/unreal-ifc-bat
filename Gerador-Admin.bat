@echo off
REM ================================================================
REM  Abre o Gerador de Batch IFC como ADMINISTRADOR.
REM  Necessario apenas se voce for usar o AGENDAMENTO automatico
REM  (schtasks do Windows exige privilegios de administrador).
REM
REM  Basta dar DUPLO-CLIQUE neste arquivo e aceitar o aviso do
REM  Windows (UAC). A interface abre ja elevada.
REM ================================================================

REM  Ja esta rodando como administrador?
net session >nul 2>&1
if %errorlevel%==0 goto :run

REM  Nao esta: reabre este proprio .bat pedindo elevacao (UAC)
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
exit /b

:run
cd /d "%~dp0"
REM  pyw = Python sem janela de console (so a GUI)
start "" pyw "%~dp0gerador.py"
exit /b
