## Why

El grafo de Graphify tiene 4.765 nodos y 7.942 aristas en 309 comunidades, pero no hay un documento legible que explique el flujo de datos a través de esas comunidades. Un desarrollador nuevo no puede entender cómo viaja una solicitud desde el Community API Controller hasta el Nurturing Email Service sin leer decenas de archivos fuente. Este documento cierra esa brecha: explica el flujo en lenguaje simple, señalando exactamente dónde está cada pieza (archivo y línea).

## What Changes

- Crear `docs/data-flow.md` que trace los pipelines de datos con diagramas de flujo simples
- Explicar cada pipeline en lenguaje no-técnico, pero referenciando la ubicación exacta de cada nodo (archivo:línea)
- Hacer 10 preguntas interactivas para recopilar contexto adicional de quienes conocen el sistema
- Documentar los nodos críticos (god nodes) y qué comunidades conectan

## Capabilities

### New Capabilities
- `data-flow-map`: Documento de flujo de datos que recorre los pipelines principales (newsletter, redes sociales, AI Radar, chat, workflows del agente) usando lenguaje claro, referencias a archivos, y preguntas para completar información faltante.

### Modified Capabilities

- (none)

## Impact

- Archivo nuevo `docs/data-flow.md`
- Sin cambios de código, APIs ni dependencias
- Fuente de información: `graphify-out/graph.json` + consultas `graphify query/path`
