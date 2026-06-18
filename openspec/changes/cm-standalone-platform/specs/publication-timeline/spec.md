## ADDED Requirements

### Requirement: Timeline visual por cliente

El sistema SHALL mostrar un timeline visual con las publicaciones de cada cliente, ordenadas cronológicamente.

#### Scenario: Ver timeline
- **WHEN** el gestor selecciona un cliente
- **THEN** el sistema muestra una línea de tiempo con publicaciones pasadas, actuales y planificadas, agrupadas por mes

### Requirement: Estados de publicación

Cada publicación en el timeline SHALL tener un estado: borrador, programada, en revisión, aprobada, publicada, fallida.

#### Scenario: Cambiar estado
- **WHEN** el gestor cambia el estado de una publicación de "borrador" a "programada"
- **THEN** el sistema agenda la publicación para la fecha/hora seleccionada y la muestra en el timeline

### Requirement: Filtros por plataforma y estado

El timeline SHALL permitir filtrar publicaciones por plataforma (Meta, TikTok, LinkedIn, X) y por estado.

#### Scenario: Filtrar timeline
- **WHEN** el gestor selecciona el filtro "TikTok" + "publicadas"
- **THEN** el timeline muestra solo publicaciones enviadas a TikTok
