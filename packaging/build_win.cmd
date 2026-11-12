@echo off
rem 在 Windows 本机构建 SealBox 目录版
setlocal
cd /d "%~dp0.."
python packaging\build.py
if errorlevel 1 exit /b 1
echo.
echo 产物：dist\SealBox\SealBox.exe（目录版）
