## ADDED Requirements

### Requirement: Dashboard del gestor

El frontend SHALL mostrar un dashboard principal con resumen de clientes, publicaciones del día, facturación del mes y alertas.

#### Scenario: Dashboard cargado
- **WHEN** el gestor inicia sesión
- **THEN** el dashboard muestra tarjetas con: total de clientes, publicaciones de hoy, ingresos del mes, suscripciones vencidas

### Requirement: Navegación lateral

El frontend SHALL tener una barra de navegación lateral con secciones: Clientes, Timeline, Facturación, Configuración.

#### Scenario: Navegar entre secciones
- **WHEN** el gestor hace clic en "Clientes"
- **THEN** la interfaz navega a la lista de clientes sin recargar la página (SPA)

### Requirement: Vista de detalle de cliente

Cada cliente SHALL tener una página de detalle con: datos del cliente, redes sociales vinculadas, timeline de publicaciones, facturas, y preferencias editoriales.

#### Scenario: Ver detalle de cliente
- **WHEN** el gestor hace clic en un cliente de la lista
- **THEN** la interfaz muestra la página de detalle con todas las secciones del cliente

### Requirement: Modo responsive

El frontend SHALL ser usable en desktop y tablet.

#### Scenario: Responsive design
- **WHEN** el gestor usa una tablet en orientación horizontal
- **THEN** todos los componentes se reordenan para ajustarse al ancho de pantalla sin perder funcionalidad
