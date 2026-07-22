Push-Location $PSScriptRoot

$git = "C:\Program Files\Git\cmd\git.exe"

Write-Output "Using git: $git"

# Ensure remote is correctly set
$remotes = & $git remote
if ($remotes -contains "origin") {
    & $git remote set-url origin https://github.com/utshadhar/psa-telegram-notifier.git
} else {
    & $git remote add origin https://github.com/utshadhar/psa-telegram-notifier.git
}
& $git config user.name "utshadhar"
& $git config user.email "utsha.dhar31@gmail.com"

Write-Output "Adding changes..."
& $git add -A
Write-Output "Committing..."
& $git commit -m "Update notifier with simplified configurations, Render endpoints, and docs"
Write-Output "Force pushing to main branch..."
& $git push origin master:main --force
Write-Output "Done!"
Pop-Location
Pause
