## ADDED Requirements

### Requirement: Suscripciones mensuales por cliente

Cada cliente SHALL tener una suscripción mensual con fecha de inicio, monto, método de pago y estado (activa, pausada, cancelada, vencida).

#### Scenario: Crear suscripción
- **WHEN** el gestor asigna un plan mensual a un cliente nuevo
- **THEN** el sistema crea la suscripción con fecha de próximo pago en 30 días

#### Scenario: Cliente se atrasa
- **WHEN** la suscripción de un cliente supera los 5 días de vencimiento
- **THEN** el sistema marca la suscripción como "vencida" y pausa la generación de contenido para ese cliente

### Requirement: Histórico de facturación

El sistema SHALL mantener un histórico de todas las facturas emitidas por cliente.

#### Scenario: Ver facturas
- **WHEN** el gestor abre la sección de facturación de un cliente
- **THEN** el sistema muestra todas las facturas emitidas, su estado (pagada, pendiente, cancelada) y enlace al comprobante

### Requirement: Notificaciones de vencimiento

El sistema SHALL notificar al gestor cuando una suscripción esté próxima a vencer (3 días antes) o haya vencido.

#### Scenario: Notificación próxima a vencer
- **WHEN** faltan 3 días para el vencimiento de una suscripción
- **THEN** el sistema envía una notificación al gestor (email/in-app)
