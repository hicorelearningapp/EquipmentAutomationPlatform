@echo off
REM A short tour: starts the backend once, sends several requests, stops it.
REM Double-click this file, or run it from a command prompt.

REM The projects that came with this folder. Remove this line to use
REM %LOCALAPPDATA%\HiCore\BraceLink instead, which is where an installed app keeps them.
set EAP_DATA_DIR=%~dp0data

REM The AI service. Analysis, questions and auto-mapping need a key; the tour runs without one.
if "%GROQ_API_KEY%"=="" set GROQ_API_KEY=
if "%LLM_PROVIDER%"=="" set LLM_PROVIDER=groq
if "%LLM_MODEL_NAME%"=="" set LLM_MODEL_NAME=openai/gpt-oss-120b

cd /d "%~dp0"
REM -E: ignore PYTHON* variables, which on some machines point at another Python.
runtime\eap_cli.exe -E demo.py

echo.
pause
