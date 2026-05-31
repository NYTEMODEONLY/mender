@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0Start-Mender.ps1" %*
