# PowerShell compilation script for SML Generation Endpoint Workflow

$files = @(
    "eap_bot/source/routers/tool_characterization_routes.py",
    "eap_bot/source/managers/service_container.py",
    "eap_bot/source/services/sml_generation_service.py",
    "eap_bot/source/services/storage_service.py",
    "eap_bot/source/schemas/secsgem.py",
    "eap_bot/source/schemas/report.py",
    "eap_bot/source/schemas/project.py"
)

$outputFile = "exports/compiled_sml_generation_code.txt"
$codebaseDir = Get-Location

# Ensure exports directory exists
New-Item -ItemType Directory -Force -Path "exports" | Out-Null

$divider = "=" * 80
$outputContent = ""

foreach ($file in $files) {
    $fullPath = Join-Path $codebaseDir $file
    if (Test-Path $fullPath) {
        Write-Host "Compiling: $file"
        $fileContent = Get-Content -Raw -Encoding utf8 -Path $fullPath
        
        $outputContent += "$divider`r`n"
        $outputContent += "--- FILE PATH: $file ---`r`n"
        $outputContent += "$divider`r`n`r`n"
        $outputContent += $fileContent
        $outputContent += "`r`n`r`n`r`n"
    } else {
        Write-Warning "File not found: $file"
    }
}

# Write compiled output
[System.IO.File]::WriteAllText((Join-Path $codebaseDir $outputFile), $outputContent, [System.Text.Encoding]::UTF8)
Write-Host "Success! Compiled file saved to: $outputFile"
