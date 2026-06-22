@echo off
set "OUTPUT_FILE=e:\Github\EquipmentAutomationPlatforms\exports\compiled_sml_generation_code.txt"

if not exist e:\Github\EquipmentAutomationPlatforms\exports mkdir e:\Github\EquipmentAutomationPlatforms\exports

echo ================================================================================ > "%OUTPUT_FILE%"
echo --- FILE PATH: eap_bot/source/routers/tool_characterization_routes.py --- >> "%OUTPUT_FILE%"
echo ================================================================================ >> "%OUTPUT_FILE%"
type e:\Github\EquipmentAutomationPlatforms\eap_bot\source\routers\tool_characterization_routes.py >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"

echo ================================================================================ >> "%OUTPUT_FILE%"
echo --- FILE PATH: eap_bot/source/managers/service_container.py --- >> "%OUTPUT_FILE%"
echo ================================================================================ >> "%OUTPUT_FILE%"
type e:\Github\EquipmentAutomationPlatforms\eap_bot\source\managers\service_container.py >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"

echo ================================================================================ >> "%OUTPUT_FILE%"
echo --- FILE PATH: eap_bot/source/services/sml_generation_service.py --- >> "%OUTPUT_FILE%"
echo ================================================================================ >> "%OUTPUT_FILE%"
type e:\Github\EquipmentAutomationPlatforms\eap_bot\source\services\sml_generation_service.py >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"

echo ================================================================================ >> "%OUTPUT_FILE%"
echo --- FILE PATH: eap_bot/source/services/storage_service.py --- >> "%OUTPUT_FILE%"
echo ================================================================================ >> "%OUTPUT_FILE%"
type e:\Github\EquipmentAutomationPlatforms\eap_bot\source\services\storage_service.py >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"

echo ================================================================================ >> "%OUTPUT_FILE%"
echo --- FILE PATH: eap_bot/source/schemas/secsgem.py --- >> "%OUTPUT_FILE%"
echo ================================================================================ >> "%OUTPUT_FILE%"
type e:\Github\EquipmentAutomationPlatforms\eap_bot\source\schemas\secsgem.py >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"

echo ================================================================================ >> "%OUTPUT_FILE%"
echo --- FILE PATH: eap_bot/source/schemas/report.py --- >> "%OUTPUT_FILE%"
echo ================================================================================ >> "%OUTPUT_FILE%"
type e:\Github\EquipmentAutomationPlatforms\eap_bot\source\schemas\report.py >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"

echo ================================================================================ >> "%OUTPUT_FILE%"
echo --- FILE PATH: eap_bot/source/schemas/project.py --- >> "%OUTPUT_FILE%"
echo ================================================================================ >> "%OUTPUT_FILE%"
type e:\Github\EquipmentAutomationPlatforms\eap_bot\source\schemas\project.py >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"
echo. >> "%OUTPUT_FILE%"

echo Compilation successful! File saved to %OUTPUT_FILE%
