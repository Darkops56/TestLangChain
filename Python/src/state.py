from typing import TypedDict, List, Dict

class ContenidoPlataforma(TypedDict):
    texto: str
    prompt_imagen: str
    aprobado_por_ia: bool
    errores: List[str]

class EstadoProyecto(TypedDict):
    prompt_usuario: str
    plataformas_destino: List[str]
    publicaciones: Dict[str, ContenidoPlataforma]
    intentos: int
    aprobado_por_humano: bool
