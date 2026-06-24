## Why

El proyecto actual combina dos dominios distintos (Community Manager y Chatbot con IA) en un mismo código base, lo que genera acoplamiento innecesario, complejidad en deploys y dificultad para escalar. Community Manager es el producto prioritario y necesita su propia plataforma con frontend, gestión de clientes, facturación y timeline de publicaciones.

## What Changes

- **BREAKING**: El monorepo actual se divide en dos repositorios completamente independientes: `cm-platform/` (Community Manager) y `chatbot-service/` (Chatbot con IA)
- **BREAKING**: Ambos proyectos NO comparten código, carpetas, librerías ni dependencias. El código compartido actual (`.env`, protocolo HTTP, API key interna, lógica duplicada Python/C#) se extrae en un archivo por proyecto conteniendo **solo lo que cada proyecto necesita**, sin shared-core
- **BREAKING**: El proyecto actual (`TestLangChain`) se convierte en `chatbot-service/` (se renombra)
- **NUEVO**: Crear `cm-platform/` con `cm-backend/` (API REST .NET) y `cm-frontend/` (Blazor WebAssembly)
- **NUEVO**: Crear `cm-frontend/` con interfaz web (Blazor) para el gestor de comunidades
- **NUEVO**: Sistema de gestión de clientes (CRUD + cuentas de redes sociales vinculadas)
- **NUEVO**: Timeline visual de publicaciones por cliente (histórico + planificadas)
- **NUEVO**: Sistema de facturación por cliente (suscripciones mensuales, pagos)
- **NUEVO**: Autenticación y roles para el proveedor del servicio

## Capabilities

### New Capabilities
- `project-separation`: Dividir el monorepo actual en dos proyectos totalmente independientes (`cm-platform/` y `chatbot-service/`). Sin código compartido, sin carpetas comunes, sin dependencias cruzadas. Cada proyecto tiene su propio stack, su propio ciclo de vida y su propio deploy
- `chatbot-migration`: Migrar `chatbot-service/` a su propio repositorio, renombrando el proyecto actual. Todo el código del chatbot funciona exactamente igual pero en aislamiento total
- `cm-agent-backend`: Crear el backend del CM (API .NET 10) con endpoints para el agente Python de Community Manager, más los endpoints de clientes, redes sociales, timeline y facturación
- `cm-agent-worker`: El agente Python del CM se despliega como worker independiente, comunicándose con `cm-backend` vía API
- `client-management`: CRUD completo de clientes con datos de contacto, redes sociales vinculadas (Meta, TikTok, LinkedIn), preferencias editoriales y estado de suscripción
- `publication-timeline`: Vista de timeline por cliente mostrando publicaciones pasadas, actuales y planificadas, con filtros por plataforma y estado
- `billing-system`: Gestión de suscripciones mensuales, facturación por cliente, histórico de pagos y notificaciones de vencimiento
- `cm-frontend`: Interfaz web (Blazor WebAssembly) para que el gestor de comunidades administre clientes, revise timelines, apruebe contenido y gestione facturación
- `auth-provider`: Autenticación del proveedor del servicio con roles (admin, gestor, facturación), login seguro y recuperación de contraseña

### Modified Capabilities

- (none - no existing specs to modify)

## Impact

- El monorepo `TestLangChain` se renombra a `chatbot-service/` y se mueve a su propio repositorio
- Se crea `cm-platform/` como repositorio nuevo con 3 sub-proyectos: `cm-backend/` (API .NET), `cm-agent/` (worker Python), `cm-frontend/` (Blazor WebAssembly)
- NO existe `shared-core/` — cada proyecto tiene su propia copia exacta de lo que necesita (extracción controlada, no duplicación ciega)
- Se añaden tablas de clientes, facturación, timeline en PostgreSQL
- Se añade autenticación JWT en `cm-backend/`
- Cada repositorio tiene su propio Docker Compose y su propio CI/CD
- No hay dependencias entre repositorios; se comunican solo vía HTTP si es necesario
