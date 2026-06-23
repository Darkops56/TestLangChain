# logs/

Esta carpeta contiene los logs persistentes de ahorro de tokens generados por Headroom-AI.

## headroom_savings.csv

Se genera automáticamente la primera vez que se ejecuta el agente con headroom-ai instalado.

Columnas:
- `timestamp`: Fecha y hora de la llamada al LLM (ISO 8601)
- `input_tokens_before`: Tokens de entrada antes de la compresión Headroom
- `input_tokens_after`: Tokens de entrada después de la compresión (lo que se envía realmente al LLM)
- `input_saved_tokens`: Tokens de entrada ahorrados por la compresión
- `input_savings_pct`: Porcentaje de ahorro en entrada (0-100)
- `output_tokens`: Tokens generados por el LLM en su respuesta
- `total_tokens`: Suma de input_tokens_after + output_tokens (consumo real total por llamada)
- `token_budget`: Presupuesto de tokens configurado (HEADROOM_TOKEN_BUDGET)
