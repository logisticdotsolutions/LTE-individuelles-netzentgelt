@echo off
setlocal
call 01_DRY_RUN_DUMMY_UI_CLASSIFICATION_V2.bat || exit /b 1
call 02_APPLY_DUMMY_UI_CLASSIFICATION_V2.bat || exit /b 1
call 03_VERIFY_DUMMY_UI_CLASSIFICATION_V2.bat || exit /b 1
call 04_RUN_DUMMY_UI_CLASSIFICATION_V2_TESTS.bat || exit /b 1
echo.
echo OK: Installation und lokale Tests erfolgreich.
echo Fuehre die Pipeline danach bewusst separat mit 05_RUN_PIPELINE_AND_VERIFY_DUMMY_UI_CLASSIFICATION_V2.bat aus.
exit /b 0
