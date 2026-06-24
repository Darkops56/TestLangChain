## ADDED Requirements

### Requirement: CRUD de clientes

El sistema SHALL permitir crear, leer, actualizar y eliminar clientes desde la interfaz del gestor.

#### Scenario: Crear cliente
- **WHEN** el gestor completa el formulario de nuevo cliente con nombre, email, teléfono y redes sociales
- **THEN** el sistema crea el cliente en la base de datos y lo muestra en la lista de clientes

#### Scenario: Editar cliente
- **WHEN** el gestor modifica los datos de un cliente existente
- **THEN** el sistema actualiza el registro y muestra confirmación

### Requirement: Redes sociales vinculadas por cliente

Cada cliente SHALL tener una o más cuentas de redes sociales asociadas (Meta, TikTok, LinkedIn, X).

#### Scenario: Vincular red social
- **WHEN** el gestor agrega una cuenta de Instagram a un cliente
- **THEN** el sistema almacena el token de acceso, el username y la plataforma, y verifica la conexión contra la API de Meta

### Requirement: Preferencias editoriales por cliente

Cada cliente SHALL almacenar preferencias editoriales (tono, frecuencias, temas prohibidos, audiencia target).

#### Scenario: Configurar preferencias
- **WHEN** el gestor edita las preferencias editoriales de un cliente
- **THEN** el sistema guarda las preferencias y las inyecta como contexto en el agente strategist para ese cliente
