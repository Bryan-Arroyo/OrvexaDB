# Seguridad y administración

La seguridad efectiva se aplica en FastAPI; la interfaz solo refleja el estado y los permisos. `.env` está ignorado por Git y no se copia a las imágenes.

## Contraseñas y usuarios

Las contraseñas se validan entre 12 y 128 caracteres y se almacenan con Argon2id mediante `pwdlib[argon2]`. Se permite una frase de contraseña y no se exige una combinación artificial de símbolos. El login usa un hash ficticio cuando el usuario no existe y responde con el mismo mensaje genérico para usuario incorrecto, contraseña incorrecta o usuario inactivo.

El primer administrador se crea interactivo:

```powershell
docker compose exec -it api python -m app.cli.create_admin
```

El comando solicita usuario, correo y contraseña dos veces con entrada oculta; normaliza usuario/correo, rechaza duplicados, no acepta la contraseña como argumento y registra solo la acción. No existe cuenta predeterminada. Los usuarios creados o restablecidos quedan con `must_change_password=true`.

## Sesiones, cookies y CSRF

Cada login crea un token opaco con al menos 32 bytes aleatorios. Solo se guarda su SHA-256 en `user_sessions`; también se guarda únicamente el hash del token CSRF independiente. La sesión caduca tras 5 minutos sin actividad real y se renueva mediante `POST /auth/activity`, con un tope absoluto de `AUTH_SESSION_HOURS` (por defecto, 8 horas). No se usan JWT ni refresh tokens.

La portada y `/login` siempre muestran el formulario y limpian el marcador de visita anterior. El frontend guarda un marcador solo en `sessionStorage` tras un login correcto; una ruta protegida abierta sin ese marcador redirige a `/login`. El marcador se borra al cerrar sesión o caducar.

| Cookie | HttpOnly | SameSite | Secure | Path |
|---|---|---|---|---|
| `orvexadb_session` | sí | `Lax` | `AUTH_COOKIE_SECURE` | `/` |
| `orvexadb_csrf` | no, para que el navegador pueda leerla | `Lax` | igual que la sesión | `/` |

Toda operación autenticada que cambia estado exige sesión, cookie CSRF, `X-CSRF-Token` coincidente y `Origin` permitido. El login también valida `Origin`. En producción o con orígenes HTTPS, `AUTH_COOKIE_SECURE=true` es obligatorio.

## Limitación de intentos

PostgreSQL registra una ventana de 15 minutos y bloquea durante 15 minutos al quinto fallo. La clave es un HMAC de identificador normalizado y la dirección entregada directamente por el servidor; no se confía en `X-Forwarded-For` sin un proxy confiable configurado. Si se despliega detrás de un proxy inverso, primero debe definirse una lista explícita de proxies confiables para la instalación y validarse cada salto; nunca se debe habilitar confianza global en `X-Forwarded-For`. La configuración actual no define ningún proxy. `AUTH_PEPPER` es específico de esta función y debe tener al menos 32 caracteres aleatorios.

## Autorización y auditoría

La dependencia `require_permission(...)` carga la sesión, comprueba usuario activo, expiración y revocación, y consulta el permiso en PostgreSQL. Devuelve `401` sin sesión válida y `403` sin permiso. No acepta permisos enviados por el frontend.

Los cambios relevantes escriben `audit_logs` dentro de la misma transacción: login, logout, bloqueos y fallos relevantes; creación, edición, activación y desactivación empresarial; movimientos; creación y cambios de usuarios; y cambios/restablecimientos de contraseña. La recepción de compras bloquea la orden y los productos, enlaza cada movimiento a una línea con restricción UNIQUE y registra auditoría, por lo que reintentos y concurrencia no duplican stock. Solo se admite recepción completa; no hay recepciones parciales. Nunca se registran contraseñas, hashes, tokens, cookies, secretos, cadenas de conexión ni cuerpos completos.

El middleware añade `x-correlation-id` y registra excepciones inesperadas con ese identificador. El cliente recibe solo un error interno genérico, sin trazas ni rutas internas.

## Variables

| Variable | Uso |
|---|---|
| `DATABASE_URL` | URL PostgreSQL de la API |
| `AUTH_PEPPER` | secreto HMAC de rate limit; obligatorio, aleatorio y no versionable |
| `AUTH_COOKIE_SECURE` | `false` solo para HTTP local; `true` con HTTPS |
| `AUTH_SESSION_HOURS` | expiración absoluta de sesión, entre 1 y 8 |
| `ALLOWED_ORIGINS` | lista separada por comas; desarrollo: `http://localhost:3000` |
| `ENVIRONMENT` | entorno; producción exige cookie segura |

Para generar un pepper local sin imprimirlo en pantalla:

```powershell
$pepper = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
(Get-Content .env) -replace '^AUTH_PEPPER=.*$', "AUTH_PEPPER=$pepper" | Set-Content .env
Remove-Variable pepper
```

## Restablecer una demostración

No borres `orvexadb_pgdata` para restablecer la base principal. Crea una copia de `.env.example` para un entorno de demostración, usa un nombre de proyecto Compose distinto (por ejemplo `orvexadb_demo`) y un pepper generado localmente. El volumen prefijado por ese proyecto es independiente. Aplica migraciones y seed, crea el administrador mediante el CLI interactivo y, al terminar, detén los servicios con `docker compose -p orvexadb_demo down` sin `-v`. No publiques el archivo `.env` ni credenciales en el repositorio.

No existe limpieza automática de `login_attempts`, `user_sessions` o `audit_logs`. Para una fase posterior, definir y probar una tarea administrativa separada con estas políticas: eliminar intentos de login con más de 30 días, eliminar sesiones expiradas o revocadas con más de 30 días, y conservar auditorías durante al menos 12 meses antes de una purga revisada. La tarea debe ejecutarse con una cuenta de mantenimiento, registrar su resultado y excluir auditorías recientes y datos de usuarios. No se documenta una operación destructiva sobre ningún volumen.

## Alcance y riesgos pendientes

Esta instalación soporta una sola base PostgreSQL y una sola empresa. La gestión de varias bases o empresas queda fuera de la Fase 2 y necesita diseño y pruebas propios. Esta fase no afirma cumplimiento absoluto de OWASP. La aplicación no incluye OAuth, LAN confiable, rotación automática de secretos, interfaz de consulta de auditoría, importación/exportación ni API de backup/restauración; el respaldo operativo usado en la validación final fue externo a la aplicación. Antes de exponer el sistema fuera del entorno local deben configurarse HTTPS, cookies seguras, gestión de secretos y una lista explícita de proxies confiables; después deben revisarse cabeceras y política de despliegue.
