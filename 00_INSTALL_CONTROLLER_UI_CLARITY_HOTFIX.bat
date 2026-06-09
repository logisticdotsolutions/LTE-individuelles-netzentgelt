@echo off
setlocal
call 01_DRY_RUN_CONTROLLER_UI_CLARITY_HOTFIX.bat || exit /b 1
call 02_APPLY_CONTROLLER_UI_CLARITY_HOTFIX.bat || exit /b 1
call 03_VERIFY_CONTROLLER_UI_CLARITY_HOTFIX.bat || exit /b 1
call 04_RUN_CONTROLLER_UI_CLARITY_HOTFIX_TESTS.bat || exit /b 1
echo OK: Installation und Tests erfolgreich.
