@echo off
REM One request, one answer. The same endpoints BraceLink calls, with no web server.
REM
REM   eap_cli.cmd GET /GetAllProjects
REM   eap_cli.cmd GET /LoadProject/3
REM   eap_cli.cmd POST /CreateProject @sample\create_project.json      (body from a file)
REM   eap_cli.cmd POST /CreateProject "{\"ProjectName\": \"Demo\", \"VendorName\": \"HiCore\", \"ProjectCode\": \"D-1\"}"
REM   eap_cli.cmd --list                                               (every endpoint)
REM
REM In PowerShell, type .\eap_cli.cmd and put an inline body in single quotes instead.
REM
REM Each run starts the backend again, which takes a few seconds. An application keeps it
REM open instead (--serve) and sends many requests to the same running copy; see README.txt.
REM
REM Only the answer is printed. The log lines go to data\logs\console.log.
REM To see them on screen as well:  set EAP_VERBOSE=1   (in PowerShell: $env:EAP_VERBOSE=1)

REM Double-clicked, or typed with nothing after it: say what to do and keep the window open.
if "%~1"=="" goto :usage

REM The projects that came with this folder. Remove this line to use
REM %LOCALAPPDATA%\HiCore\BraceLink instead, which is where an installed app keeps them.
if "%EAP_DATA_DIR%"=="" set EAP_DATA_DIR=%~dp0data

REM The AI service. Analysis, questions and auto-mapping need a key; everything else does not.
if "%GROQ_API_KEY%"=="" set GROQ_API_KEY=
if "%LLM_PROVIDER%"=="" set LLM_PROVIDER=groq
if "%LLM_MODEL_NAME%"=="" set LLM_MODEL_NAME=openai/gpt-oss-120b

REM -E: ignore PYTHON* variables, which on some machines point at another Python.
"%~dp0runtime\eap_cli.exe" -E "%~dp0eap_bot\eap_cli.py" %*
goto :eof

:usage
echo.
echo   HiCore EAP backend - one request, one answer.
echo.
echo   This needs a method and a path after it, so double-clicking cannot do anything
echo   on its own. Nothing is broken.
echo.
echo   For a tour that runs by itself, double-click  demo.cmd  instead.
echo.
echo   To send requests yourself, open a terminal in this folder
echo   (right-click an empty spot - Open in Terminal) and type:
echo.
echo       .\eap_cli.cmd GET /GetAllProjects
echo       .\eap_cli.cmd GET /LoadProject/3
echo       .\eap_cli.cmd --list
echo       .\eap_cli.cmd POST /CreateProject @sample\create_project.json
echo.
echo   HOW_TO_TRY_IT.md explains all of it, including how BraceLink uses the same file.
echo.
pause
