# Modelo de datos

Las tablas se encuentran en el esquema PostgreSQL activo. `0001_initial` crea la base; `0002_auth` añade seguridad de usuarios/sesiones; `0003_domain` añade índices de consulta y la descripción de movimientos. Los identificadores son UUID generados por la aplicación. Las marcas temporales usan zona horaria y `DEFAULT now()` cuando se indica.

`0004_purchase_orders` añade órdenes de compra y recepción idempotente.

La revisión se encuentra aplicada en la instalación local validada. Tras la migración, las tablas `purchase_orders` y `purchase_order_lines` quedaron vacías y los seis recuentos de datos previos comprobados se conservaron.

`inventory_movements.purchase_order_line_id` enlaza cada movimiento de recepción con su línea y tiene una restricción UNIQUE. `purchase_orders` conserva el proveedor y total; `purchase_order_lines` conserva SKU, nombre, cantidad, coste y total de cada línea.

La columna `purchase_order_line_id` es una FK opcional a `purchase_order_lines` y UNIQUE: una línea de compra solo puede producir un movimiento de recepción.

## Tablas, columnas y restricciones

`*` significa `NOT NULL`; las columnas sin `*` aceptan `NULL`.

| Tabla | Columnas | Claves, índices e invariantes |
|---|---|---|
| `roles` | `id* UUID`, `name* VARCHAR(80)`, `created_at*`, `updated_at*` | PK `id`; UNIQUE `name` |
| `permissions` | `id* UUID`, `code* VARCHAR(100)`, `created_at*`, `updated_at*` | PK `id`; UNIQUE `code` |
| `role_permissions` | `role_id* UUID`, `permission_id* UUID` | PK compuesta; FK a `roles` y `permissions` |
| `users` | `id* UUID`, `username* VARCHAR(80)`, `email* VARCHAR(320)`, `password_hash* VARCHAR(255)`, `is_active*`, `must_change_password*`, `last_login_at TIMESTAMPTZ`, `role_id* UUID`, `created_at*`, `updated_at*` | PK; UNIQUE `username` y `email`; FK obligatoria a `roles`; usuario y correo en minúsculas |
| `user_sessions` | `id* UUID`, `user_id* UUID`, `token_hash* VARCHAR(128)`, `csrf_token_hash* VARCHAR(64)`, `created_at*`, `expires_at*`, `revoked_at TIMESTAMPTZ` | PK; UNIQUE `token_hash`; FK a `users`; índices por `user_id`, `expires_at` y `token_hash`; nunca guarda tokens en claro |
| `login_attempts` | `id* UUID`, `key_hmac* VARCHAR(64)`, `window_started_at*`, `failure_count* INTEGER`, `blocked_until TIMESTAMPTZ`, `updated_at*` | PK; UNIQUE e índice `key_hmac`; `failure_count >= 0`; la clave es HMAC, no una IP |
| `categories` | `id* UUID`, `code* VARCHAR(40)`, `name* VARCHAR(120)`, `is_active*`, `created_at*`, `updated_at*` | PK; UNIQUE `code`; índice `(is_active, name)`; código en mayúsculas |
| `suppliers` | `id* UUID`, `code* VARCHAR(40)`, `name* VARCHAR(160)`, `is_active*`, `created_at*`, `updated_at*` | PK; UNIQUE `code`; índice `(is_active, name)`; código en mayúsculas |
| `products` | `id* UUID`, `sku* VARCHAR(80)`, `name* VARCHAR(160)`, `category_id UUID`, `supplier_id UUID`, `stock_current* NUMERIC(12,2)`, `minimum_stock* NUMERIC(12,2)`, `unit_cost* NUMERIC(12,2)`, `is_active*`, `created_at*`, `updated_at*` | PK; UNIQUE `sku`; FKs opcionales a categorías/proveedores; índices `(is_active,name)`, `category_id`, `supplier_id`; stock, mínimo y coste `>= 0`; SKU en mayúsculas |
| `inventory_movements` | `id* UUID`, `product_id* UUID`, `user_id UUID`, `quantity* NUMERIC(12,2)`, `direction* VARCHAR(8)`, `reason* VARCHAR(30)`, `description VARCHAR(240)`, `occurred_at*` | PK; FK a `products` y FK opcional a `users`; índices `product_id` y `occurred_at`; `quantity > 0`; dirección `in/out`; motivo `purchase/sale/adjustment/return` |
| `purchase_orders` | `id* UUID`, `order_number* VARCHAR(40)`, `supplier_id* UUID`, `supplier_name* VARCHAR(160)`, `status*`, `total* NUMERIC(14,2)`, `created_by* UUID`, `created_at*`, `updated_at*` | PK; número UNIQUE; FK a proveedor y usuario; estados `draft/confirmed/received/canceled`; total no negativo |
| `purchase_order_lines` | `id* UUID`, `purchase_order_id* UUID`, `product_id* UUID`, `product_sku* VARCHAR(80)`, `product_name* VARCHAR(160)`, `quantity* NUMERIC(12,2)`, `unit_cost* NUMERIC(12,2)`, `line_total* NUMERIC(14,2)` | PK; FK a orden y producto; snapshot histórico del producto; cantidad positiva y coste no negativo |
| `audit_logs` | `id* UUID`, `actor_user_id UUID`, `action* VARCHAR(80)`, `entity* VARCHAR(80)`, `result* VARCHAR(30)`, `entity_id VARCHAR(100)`, `metadata_json JSONB`, `created_at*` | PK; FK opcional a `users`; no contiene contraseñas, hashes, tokens, cookies ni secretos |
| `data_jobs` | `id* UUID`, `job_type*`, `status*`, `processed_count*`, `accepted_count*`, `rejected_count*`, `created_at*` | PK; contadores no negativos; no hay API de importación/exportación en esta fase |
| `data_job_errors` | `id* UUID`, `job_id* UUID`, `row_number*`, `field`, `message*` | PK; FK a `data_jobs`; `row_number > 0` |
| `backup_runs` | `id* UUID`, `checksum`, `size_bytes`, `status*`, `created_at*` | PK; `size_bytes` nulo o no negativo; no hay operación de backup/restauración en esta fase |

Las relaciones no usan borrado en cascada. El movimiento creado por el seed puede tener `user_id = NULL` porque representa una carga del sistema.

## Invariantes de negocio

- No se borran físicamente categorías, proveedores, productos, usuarios ni movimientos; se conserva el historial y se usa `is_active` o revocación.
- `stock_current`, `minimum_stock` y `unit_cost` no son negativos. El stock de un producto no se acepta en el CRUD general.
- Un producto con `stock_current <= minimum_stock` aparece como stock bajo.
- Todo movimiento válido bloquea su producto con `SELECT ... FOR UPDATE`, comprueba actividad y saldo, inserta el movimiento, actualiza el saldo y registra auditoría en una misma transacción. Un fallo revierte el conjunto completo.
- El seed mantiene roles, permisos y datos DEMO idempotentes.
- Las órdenes conservan snapshots de proveedor, SKU y nombre. Solo se permite recepción completa; las recepciones parciales quedan fuera de esta fase.

## Fase 2 y fases posteriores

La Fase 2 genera auditoría interna, pero no ofrece consulta administrativa de esos registros. Importación, exportación, backups/restauración y la interfaz administrativa de auditoría quedan fuera de esta fase.
