# Estrategia de pruebas

## Comprobaciones locales

API:

```powershell
cd apps/api
uv sync --frozen --extra test
uv run ruff check .
uv run pytest -q -p no:cacheprovider
```

Frontend:

```powershell
cd apps/web
npm ci
npm run lint
npm run typecheck
npm test
```

Versiones verificadas en la validación de Fase 2: Next.js `16.4.2` y `@playwright/test` `1.64.1`. La API mantiene las versiones fijadas en `apps/api/pyproject.toml` y `uv.lock`.

## Suite backend con PostgreSQL aislado

La validación histórica de Fase 2 usó el proyecto `orvexadb_fase2_backend`. La validación de Fase 3 usa `orvexadb_fase3_backend`, contra una base PostgreSQL exclusiva; el esquema efímero lo prepara el fixture y se elimina al finalizar. La base principal y su volumen no se usan.

```powershell
$backendProject = 'orvexadb_fase3_backend'
docker compose -p $backendProject up -d --build db api
docker compose -p $backendProject exec -T db sh -lc 'createdb -U "$POSTGRES_USER" orvexadb_test 2>/dev/null || true'
docker compose -p $backendProject run --rm --no-deps --user root api sh -lc 'export TEST_DATABASE_URL="${DATABASE_URL%/*}/orvexadb_test"; uv sync --frozen --extra test --quiet; .venv/bin/pytest -q -p no:cacheprovider'
docker compose -p $backendProject down
```

El nombre `orvexadb_test` debe existir únicamente en el PostgreSQL de ese proyecto; si el entorno de prueba usa otro nombre, ajusta solo `TEST_DATABASE_URL` dentro del contenedor. No apuntes esta variable a la base principal. `down` retira los servicios y conserva el volumen aislado; no uses `down -v` ni comandos de borrado de volúmenes.

## PostgreSQL aislado

Las pruebas de integración requieren PostgreSQL real y una base separada indicada por `TEST_DATABASE_URL`. El fixture crea un esquema UUID efímero, configura Alembic contra ese esquema y elimina el esquema al finalizar. No llama a un `get_settings()` cacheado para elegir la URL y no usa SQLite.

Para una ejecución Docker separada de Fase 2 se usó `orvexadb_fase2_e2e`. La validación inicial de Fase 3 usa `orvexadb_fase3_e2e`; la ejecución E2E final se realizó en el proyecto nuevo `orvexadb_fase3_final_e2e`, separado de `orvexadb_pgdata`:

```powershell
$e2eProject = 'orvexadb_fase3_final_e2e'
docker compose -p $e2eProject up -d db api web
docker compose -p $e2eProject exec api alembic upgrade head
docker compose -p $e2eProject exec api python -m app.seed
docker compose -p $e2eProject exec -it api python -m app.cli.create_admin
```

El último comando es interactivo: solicita el primer usuario administrador y su contraseña sin eco. Usa únicamente datos ficticios y no guardes ni publiques esa contraseña. `alembic upgrade head` y el seed deben ejecutarse antes de iniciar el recorrido.

`down` detiene y retira los contenedores, pero conserva el volumen separado del proyecto. No uses `down -v` ni elimines volúmenes para esta validación. En CI, la base de prueba debe ser creada con un nombre dedicado y la variable debe apuntar solo a ella.

## Cobertura de Fases 2 y 3

Backend: Argon2id, hash ficticio, login genérico, usuarios inactivos, rate limit, expiración/revocación, logout, cambio obligatorio, CSRF, `Origin`, permisos 401/403, CRUD lógico, duplicados, filtros/paginación/ordenación, stock, saldo insuficiente, concurrencia, auditoría transaccional y agregados del dashboard.
Compras: migración `0004_purchase_orders`, validación decimal, snapshots, transiciones, permisos, recepción completa transaccional, idempotencia persistente y concurrencia.

Frontend: login, sesión, cambio obligatorio, navegación por permisos, formularios de catálogo/movimientos/usuarios, dashboard y respuestas 401, 403, 409 y 429 con estados accesibles.

E2E: portada y `/login` muestran el formulario aunque exista cookie válida; login desde portada llega al dashboard; una ruta protegida sin marcador de visita redirige sin cargar datos; el timeout de 5 minutos revoca sesión y borra cookies; además del recorrido empresarial completo. Ejecutar en escritorio y en una resolución móvil, siempre con datos ficticios y un entorno aislado.

El recorrido E2E se ejecuta en el proyecto Compose aislado, con el administrador creado por el CLI y los proyectos de escritorio y móvil definidos por la configuración de Playwright. Define las variables solo en el proceso actual; la contraseña se solicita sin eco y no se escribe en un archivo ni se muestra en la salida:

```powershell
cd apps/web
$env:E2E_BASE_URL = 'http://localhost:3002'
$env:E2E_ADMIN_USERNAME = Read-Host 'Usuario administrador E2E'
$env:E2E_ADMIN_PASSWORD = [System.Net.NetworkCredential]::new('', (Read-Host 'Contraseña administrador E2E' -AsSecureString)).Password
npm run e2e
Remove-Item Env:E2E_BASE_URL,Env:E2E_ADMIN_USERNAME,Env:E2E_ADMIN_PASSWORD
```

La suite histórica de Fase 2 tenía 20 casos. La suite final de Fase 3 ejecutó 24 casos en escritorio y móvil en 18,6 segundos sobre `http://localhost:3002`, con captura móvil sin overflow. El entorno E2E usa una base y un volumen propios. Sus datos son ficticios y se conservan mientras el proyecto siga activo para permitir revisar resultados; al terminar, `docker compose -p $e2eProject down` retira los servicios sin borrar el volumen.

## Docker y persistencia

Para una instalación local futura, las pruebas locales pueden requerir un `.env` con `POSTGRES_PASSWORD` y `AUTH_PEPPER` propios del entorno. En la validación de Fase 3 se usaron variables efímeras y proyectos Compose aislados; no se leyó ni modificó el `.env` principal.

Como contexto histórico de Fase 2 o prerequisito de una instalación futura, la verificación completa puede incluir construcción reproducible, `alembic upgrade head`, `alembic check`, seed idempotente, creación interactiva del primer administrador, healthchecks, login a través de `localhost:3000`, ausencia de puertos de API/PostgreSQL y persistencia tras reiniciar servicios. La Fase 3 se verificó únicamente en proyectos aislados: no se migró ni reinició la base principal, no se publicó en `localhost:3000` y no se eliminó el volumen principal.

Histórico de Fase 2: backend `28 passed, 17 warnings`, suite web Vitest `22/22` y Playwright `20 passed`. Resultados finales de Fase 3: backend `32/32` en PostgreSQL aislado, incluida la prueba focal de atomicidad reforzada; web unit `21/21`, incluida la búsqueda de proveedores y productos fuera de la primera página; lint con 0 errores y 1 advertencia preexistente; typecheck y build correctos, incluido el build Docker del web; Playwright `24/24` en 18,6 segundos en `orvexadb_fase3_final_e2e` sobre `localhost:3002`, con captura móvil sin overflow. Las validaciones usaron proyectos aislados distintos de la base principal y no modificaron `.env`.

## Validación final local de Fase 4

La base local se respaldó fuera de los proyectos y el respaldo se verificó en una base aislada antes de aplicar `0004_purchase_orders`. La migración se ejecutó con confirmación del usuario. Se comprobaron seis recuentos previos, las tablas nuevas de compras quedaron vacías y la API y la web terminaron saludables. No se introdujeron datos de prueba en la base local.

La suite aislada posterior a la migración volvió a pasar: backend PostgreSQL `32 passed, 18 warnings`; frontend lint `0 errors, 1 warning` preexistente, typecheck correcto, build correcto y Vitest `21 passed`. El E2E final de Fase 4 pasó `24/24` casos. La revisión visual pasó `2/2` viewports (`1280x800` y `393x852`), con contraste, foco, etiquetas accesibles y ausencia de desbordamiento horizontal comprobados en dashboard y compras.

## Evidencia y riesgos

Registrar comando, resultado, pruebas superadas/omitidas y duración aproximada para backend, frontend, PostgreSQL, Playwright y Docker. La auditoría de dependencias npm de producción terminó con `0` vulnerabilidades; las dependencias de desarrollo siguen siendo un riesgo separado que debe revisarse antes de publicar. Una suite verde no demuestra cumplimiento absoluto de OWASP; revisar además secretos, cookies en navegador, logs sin tokens y configuración de HTTPS antes de cualquier exposición fuera del entorno local.
