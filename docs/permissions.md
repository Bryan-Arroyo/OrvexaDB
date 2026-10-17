# Matriz de permisos y rutas

Los permisos se comprueban en FastAPI desde PostgreSQL. Ocultar un enlace en la interfaz no concede ni revoca acceso.

## Roles

| Capacidad | Administrador | Empleado |
|---|---:|---:|
| `product.read` | sí | sí |
| `product.create` | sí | sí |
| `product.update` | sí | sí |
| `product.deactivate` | sí | no |
| `category.manage` | sí | no |
| `supplier.manage` | sí | no |
| `inventory.read` | sí | sí |
| `inventory.move` | sí | sí |
| `purchase.read` | sí | sí |
| `purchase.manage` | sí | no |
| `purchase.receive` | sí | sí |
| `user.manage` | sí | no |
| `audit.read` | sí | no |
| `backup.create` | sí | no |
| `backup.restore` | sí | no |
| `settings.manage` | sí | no |
| `data.import` | sí | no |
| `data.export` | sí | sí (seed actual) |

Los permisos de auditoría, backup, configuración e importación/exportación se conservan en el catálogo de permisos para el diseño futuro, pero sus operaciones no forman parte de la Fase 2.

## API principal

| Ruta | Operación | Permiso o condición |
|---|---|---|
| `/api/v1/auth/login` | `POST` | origen permitido; crea sesión |
| `/api/v1/auth/logout` | `POST` | sesión + CSRF |
| `/api/v1/auth/me` | `GET` | sesión |
| `/api/v1/auth/change-password` | `POST` | sesión + contraseña actual + CSRF |
| `/api/v1/admin/users` | `GET`, `POST` | `user.manage` |
| `/api/v1/admin/users/{id}` | `GET`, `PATCH` | `user.manage` |
| `/api/v1/admin/users/{id}/activate` | `POST` | `user.manage` |
| `/api/v1/admin/users/{id}/deactivate` | `POST` | `user.manage`; protege el último administrador y la sesión propia |
| `/api/v1/admin/users/{id}/reset-password` | `POST` | `user.manage` |
| `/api/v1/categories` y `/{id}` | `GET` | `product.read` |
| `/api/v1/categories` y `/{id}` | `POST`, `PATCH`, `/activate`, `/deactivate` | `category.manage` |
| `/api/v1/suppliers` y `/{id}` | `GET` | `product.read` |
| `/api/v1/suppliers` y `/{id}` | `POST`, `PATCH`, `/activate`, `/deactivate` | `supplier.manage` |
| `/api/v1/products` y `/{id}` | `GET` | `product.read` |
| `/api/v1/products` y `/{id}` | `POST` | `product.create` |
| `/api/v1/products/{id}` | `PATCH` | `product.update` |
| `/api/v1/products/{id}/activate` o `/deactivate` | `POST` | `product.deactivate` |
| `/api/v1/inventory-movements` | `GET` | `inventory.read` |
| `/api/v1/inventory-movements` | `POST` | `inventory.move` |
| `/api/v1/dashboard/summary` | `GET` | `inventory.read` |
| `/api/v1/purchase-orders` | `GET`, `/{id}` | `purchase.read` |
| `/api/v1/purchase-orders` | `POST`, `PUT /{id}`, `/{id}/confirm`, `/{id}/cancel` | `purchase.manage` |
| `/api/v1/purchase-orders/{id}/receive` | `POST` | `purchase.receive`; solo órdenes confirmadas |

Los listados usan `page`, `page_size` (máximo 100), búsqueda/filtros explícitos y columnas de ordenación permitidas. No aceptan nombres SQL arbitrarios.

## Rutas frontend

Next.js ofrece `/login`, `/dashboard`, `/products`, `/categories`, `/suppliers`, `/inventory` y `/admin/users`. Usa cookies del mismo origen, lee solo la cookie CSRF para crear el encabezado y no persiste sesiones en `localStorage` ni `sessionStorage`. Un `401` devuelve al login; un `403` se muestra como acceso denegado.
