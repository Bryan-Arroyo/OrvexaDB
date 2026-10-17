# Arquitectura

## Servicios y límites

Compose contiene tres servicios en la red privada `orvexadb`:

| Servicio | Función | Puertos publicados al host |
|---|---|---|
| `web` | Next.js con App Router y TypeScript estricto; origen visible y proxy `/api/*` | `3000:3000` |
| `api` | FastAPI, Pydantic, SQLAlchemy síncrono y Psycopg 3 | ninguno |
| `db` | PostgreSQL 18.6 Alpine | ninguno |

El navegador solo contacta con Next.js. El proxy usa `API_INTERNAL_URL` para alcanzar `http://api:8000`; PostgreSQL y FastAPI no quedan expuestos directamente. Alembic aplica las revisiones en PostgreSQL y el seed es idempotente.

## Flujo de una petición autenticada

1. Next.js reenvía `/api/v1/...` a FastAPI conservando las cookies del mismo origen.
2. FastAPI resuelve la sesión opaca desde `orvexadb_session`, carga el usuario activo y consulta sus permisos en PostgreSQL.
3. En operaciones mutables verifica `Origin`, cookie CSRF y encabezado `X-CSRF-Token`.
4. La operación y su registro de auditoría se confirman en la misma transacción cuando el cambio es empresarial.
5. La respuesta conserva `x-correlation-id`; los errores inesperados se registran en servidor sin trazas al cliente.

## Migraciones

Las revisiones de Fase 2 son `0002_auth` y `0003_domain`; `0004_purchase_orders` añade órdenes, líneas y el enlace único de movimientos de recepción. Todas son posteriores a `0001_initial`. No se modifica la revisión inicial. Antes de usar un entorno compartido, ejecutar `alembic upgrade head` y `alembic check` dentro del servicio API.

En la validación final local, `0004_purchase_orders` se aplicó después de verificar un respaldo externo. Se conservaron los seis recuentos previos comprobados y las tablas nuevas quedaron vacías; la API y la web iniciaron con healthchecks correctos.

## Decisiones deliberadas

- PostgreSQL es la única base de datos; no se añade SQLite, Redis, Celery ni un proveedor OAuth.
- Las sesiones no son JWT ni refresh tokens.
- El stock solo cambia al crear un movimiento, con bloqueo de fila del producto.
- La recepción de una orden bloquea la orden y los productos ordenados por UUID, crea movimientos únicos por línea y cambia stock y estado en una sola transacción.
- La navegación frontend ayuda a orientar al usuario, pero la autorización efectiva siempre está en FastAPI.
