## ADDED Requirements

### Requirement: Autenticación JWT

El sistema SHALL autenticar al gestor mediante JWT con access token (15 min) y refresh token (7 días).

#### Scenario: Login exitoso
- **WHEN** el gestor ingresa email y contraseña válidos
- **THEN** el sistema devuelve un access token y un refresh token, y redirige al dashboard

#### Scenario: Token expirado
- **WHEN** el access token expira y el gestor hace una petición
- **THEN** el sistema renueva automáticamente con el refresh token sin mostrar pantalla de login

### Requirement: Roles de usuario

El sistema SHALL soportar tres roles: admin (acceso total), gestor (clientes y timeline), facturación (solo facturación).

#### Scenario: Acceso por rol
- **WHEN** un usuario con rol "facturación" intenta acceder a la sección de timeline
- **THEN** el sistema deniega el acceso con código 403

### Requirement: Recuperación de contraseña

El sistema SHALL permitir recuperar la contraseña mediante email con enlace temporal (15 min de validez).

#### Scenario: Solicitar recuperación
- **WHEN** el gestor hace clic en "Olvidé mi contraseña" e ingresa su email
- **THEN** el sistema envía un email con un enlace para restablecer la contraseña
