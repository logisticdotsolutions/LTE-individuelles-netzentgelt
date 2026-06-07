@echo off
echo ================================================================
echo Netzentgelt Cancelled Hotfix - GIT COMMIT
echo ================================================================
git add scripts\run_all.py scripts\error_rules.py scripts\export_module.py app\app.py
git commit -m "Exclude cancelled transports from timeline findings and exports"
