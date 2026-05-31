@echo off
setlocal
call "%~dp0mender.cmd" %*
exit /b %errorlevel%
