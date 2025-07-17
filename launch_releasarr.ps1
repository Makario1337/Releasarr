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
Write-Host "Redis should be accessible at localhost:6379"
Write-Host ""
Write-Host "--- IMPORTANT: Start the Celery Worker ---"
Write-Host "The Celery worker runs in a separate process. You need to open a NEW terminal"
Write-Host "in your project's root directory (where main.py is located) and run:"
Write-Host ""
Write-Host "celery -A main.celery_app worker --loglevel=info"
Write-Host ""
Write-Host "Ensure Celery is installed in your local Python environment or within a separate worker container."
Write-Host "If you are running Celery in a separate container, you'll need a separate service definition in docker-compose.yml."

