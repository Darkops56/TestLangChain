# Visual Workflow

```
                          ┌──────────────┐
                          │   ENTRADA    │
                          │  "Hola" / "" │
                          └──────┬───────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │      VALIDATOR         │
                    │  ¿input está vacío?    │
                    └────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
               input válido             input vacío
                    │                         │
                    ▼                         │
          ┌──────────────────┐               │
          │    ENRICHER      │               │
          │  Agrega contexto │               │
          │  mock (simulado) │               │
          └────────┬─────────┘               │
                   │                         │
                   ▼                         ▼
          ┌──────────────────────────────────────┐
          │             RESPONDER                │
          │  Genera respuesta final (mock)       │
          └────────────────┬─────────────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   RESULTADO  │
                    │  Estado msg  │
                    └──────────────┘
```

## Flujo con input "Hola"

```
POST /workflow/run  {"input": "Hola"}
        │
        ▼
VALIDATOR → input no vacío → validated = True
        │
        ▼
ENRICHER → "Hola [enriched with context]"   ← SIMULADO
        │
        ▼
RESPONDER → "Final response for: Hola [enriched with context]"
        │
        ▼
GET /workflow/result/{run_id}
{
  "input": "Hola",
  "validated": true,
  "enriched": "Hola [enriched with context]",
  "response": "Final response for: Hola [enriched with context]",
  "messages": [
    "Validator: Input valid",
    "Enricher: Context added",
    "Responder: Response generated"
  ]
}
```

## Flujo con input "" (vacío)

```
POST /workflow/run  {"input": ""}
        │
        ▼
VALIDATOR → input vacío → validated = False
        │
        ▼
RESPONDER → (salta ENRICHER)
        │
        ▼
GET /workflow/result/{run_id}
{
  "messages": [
    "Validator: Input empty",
    "Responder: Response generated"
  ]
}
```

## ¿Por qué dice "[enriched with context]"?

Es un **mock** (simulación). El proyecto no usa LLMs reales. 
Cada nodo devuelve texto prefijado para demostrar que el flujo
pasa por los distintos agentes:

| Nodo | Mensaje |
|---|---|
| Validator | `"Validator: Input valid"` / `"Validator: Input empty"` |
| Enricher | `"Enricher: Context added"` + texto con `[enriched with context]` |
| Responder | `"Responder: Response generated"` |

Para usar IA real, reemplazarías el cuerpo de cada nodo con llamadas
a OpenAI, Claude, etc.
