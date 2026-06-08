@echo off
setlocal
git add -- requirements-test.txt pytest.ini RUN_TESTS.bat RUN_TESTS.ps1 CREATE_TEST_SUITE_COMMIT.bat tests docs .github/workflows/netzentgelt-tests.yml.example
if errorlevel 1 exit /b %ERRORLEVEL%
git commit -m "test: add automated Netzentgelt MVP regression suite" -- requirements-test.txt pytest.ini RUN_TESTS.bat RUN_TESTS.ps1 CREATE_TEST_SUITE_COMMIT.bat tests docs .github/workflows/netzentgelt-tests.yml.example
if errorlevel 1 exit /b %ERRORLEVEL%
echo PASS: Lokaler Commit erstellt. Es wurde bewusst NICHT gepusht.
