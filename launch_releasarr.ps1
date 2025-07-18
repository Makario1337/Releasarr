Set-Location -Path $PSScriptRoot

Write-Host "--- Stopping and removing old containers (if any) ---"
docker compose down --remove-orphans

Write-Host "--- Checking for and removing pre-existing 'releasarr' container by name ---"
docker rm -f releasarr 2>$null

Write-Host "--- Building Docker images for Releasarr ---"
docker compose build

if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker image build failed. Please check the Dockerfile and logs above."
    exit 1
}

Write-Host "--- Launching Releasarr and Redis containers ---"
docker compose up -d

if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker Compose failed to launch containers. Please check the docker-compose.yml and logs above."
    exit 1
}

Write-Host "--- Containers launched successfully! ---"
Write-Host "Releasarr should be accessible at http://localhost:1337"