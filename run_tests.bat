@echo off
setlocal

rem Ensure Python 3.14 path if installed in default user directory
if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" (
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python314;%LOCALAPPDATA%\Programs\Python\Python314\Scripts;%PATH%"
)

set "PYTHONPATH=.;pylibs"

echo ============================================================
echo [Step 1/2] Running Backend ^& Static Tests...
echo ============================================================
python -m pytest tests/ --ignore=tests/e2e -v --timeout=180
if errorlevel 1 (
    echo [ERROR] Backend / static tests failed! Stopping.
    exit /b 1
)

echo.
echo ============================================================
echo [Step 2/2] Running E2E Browser Tests...
echo ============================================================
python -m pytest tests/e2e -v --timeout=180
if errorlevel 1 (
    echo [ERROR] E2E browser tests failed! Stopping.
    exit /b 1
)

echo.
echo ============================================================
echo [SUCCESS] All test suites passed!
echo ============================================================
exit /b 0
