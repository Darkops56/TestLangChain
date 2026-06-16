# Sandbox de Agentes con LangChain & LangGraph

Este proyecto configura un entorno en Python y una arquitectura de pruebas robusta para desarrollar y testear **nodos** y **herramientas (tools)** con agentes utilizando **LangChain** y **LangGraph**.

## Características del Workflow

1. **Pruebas deterministas sin costo de API**: Usamos fixtures de `pytest` y mocks estructurados para simular respuestas del LLM, permitiendo validar la correcta transición de nodos y la ejecución de herramientas en milisegundos sin requerir una API Key de OpenAI.
2. **Ejecución paso a paso interactiva**: `run.py` te permite interactuar en tiempo real con el agente y observar vía consola el flujo detallado de qué nodos se activan y qué herramientas se invocan.
3. **Estructura modular limpia**: Separamos la definición del Estado, Herramientas, Nodos de lógica y la construcción del Grafo.

---

## Estructura del Directorio

```
Python/
├── .env                  # Archivo de variables de entorno locales (API Key de OpenAI)
├── requirements.txt      # Librerías (langchain, langgraph, pytest, dotenv)
├── run.py                # Script CLI para chatear interactivamente con el agente
├── src/                  # Lógica principal del agente
│   ├── state.py          # Estado que viaja por el grafo (AgentState)
│   ├── tools.py          # Herramientas decoradas con @tool (get_weather, calculator)
│   ├── nodes.py          # Nodo call_model que invoca al LLM
│   └── graph.py          # Definición y compilación de StateGraph
└── tests/                # Suite de pruebas automatizadas
    ├── conftest.py       # Fixture con el mock del LLM (mock_llm)
    ├── test_tools.py     # Pruebas unitarias de las herramientas individuales
    ├── test_nodes.py     # Pruebas unitarias de los nodos aislados
    └── test_graph.py     # Pruebas de integración del flujo del grafo
```

---

## Instrucciones de Uso

### 1. Activar el Entorno Virtual e Instalar Dependencias

Desde la terminal en el directorio `Python/`:

```powershell
# Activar entorno virtual en Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# Instalar dependencias si añades nuevas
pip install -r requirements.txt
```

### 2. Ejecutar las Pruebas Automatizadas (pytest)

Las pruebas están preparadas para simular el comportamiento de OpenAI, por lo que no es necesario que ingreses tu API Key para validarlas:

```bash
pytest tests/ -v
```

### 3. Ejecutar de forma Interactiva (Modo Real)

Para conversar con el agente y ver cómo se activan sus nodos y herramientas en vivo:

1. Crea o abre el archivo `.env` en el directorio `Python/`.
2. Introduce tu API Key de OpenAI:
   ```env
   OPENAI_API_KEY=sk-...
   ```
3. Ejecuta el script:
   ```bash
   python run.py
   ```
