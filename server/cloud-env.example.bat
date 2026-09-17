@echo off
rem Optional cloud deployment settings. Copy this file to cloud-env.local.bat and adjust as needed.
rem cloud-env.local.bat is ignored by Git, so never store it in the repository.

set "FANTASYCARD_CLOUD_HOST=43.172.70.182"
set "FANTASYCARD_CLOUD_USER=ubuntu"
set "FANTASYCARD_CLOUD_KEY=C:\Users\YOUR_WINDOWS_USER\Downloads\gpt.pem"
set "FANTASYCARD_CLOUD_UPDATE_COMMAND=~/fantasycard-update"
