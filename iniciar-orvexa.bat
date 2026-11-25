@echo off
cd /d "%~dp0"
echo Iniciando OrvexaDB...
docker info >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop no esta en marcha. Abrelo, espera a que arranque y vuelve a ejecutar este archivo.
  pause
  exit /b 1
)
echo Construyendo y arrancando servicios...
docker compose up --build -d
if errorlevel 1 goto error
echo Aplicando migraciones...
docker compose exec api alembic upgrade head
if errorlevel 1 goto error
echo Actualizando roles y permisos...
docker compose exec api python -m app.seed
if errorlevel 1 goto error
echo.
echo Listo. Abriendo http://localhost:3000 ...
timeout /t 3 >nul
start http://localhost:3000
pause
exit /b 0
:error
echo Hubo un error. Revisa el mensaje de arriba.
pause
exit /b 1
