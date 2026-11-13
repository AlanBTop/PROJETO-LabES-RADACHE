@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 RADACHE_Modulo_Alunos\backend\run_local.py %*
    goto fim
)
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys; sys.exit(sys.version_info.major != 3)" >nul 2>nul
    if not errorlevel 1 (
        python RADACHE_Modulo_Alunos\backend\run_local.py %*
        goto fim
    )
)
if exist "%LOCALAPPDATA%\Programs\pgAdmin 4\python\python.exe" (
    "%LOCALAPPDATA%\Programs\pgAdmin 4\python\python.exe" RADACHE_Modulo_Alunos\backend\run_local.py %*
    goto fim
)
echo Python 3 nao encontrado. Instale Python 3 para iniciar.
:fim
if not "%RADACHE_SEM_PAUSA%"=="1" pause
