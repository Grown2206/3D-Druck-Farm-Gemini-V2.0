@echo off
set timestamp=%date:~-4,4%%date:~-7,2%%date:~-10,2%_%time:~0,2%%time:~3,2%
set timestamp=%timestamp: =0%
copy instance\database.db backups\database_%timestamp%.db
echo Backup erstellt: database_%timestamp%.db