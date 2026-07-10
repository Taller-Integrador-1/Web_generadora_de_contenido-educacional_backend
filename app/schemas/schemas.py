from pydantic import BaseModel
from typing import Optional, List

class ChatRequest(BaseModel):
    usuario_id: str
    mensaje: str
    dify_conversation_id: Optional[str] = None
    ejercicio_titulo: Optional[str] = None
    ejercicio_descripcion: Optional[str] = None
    codigo_alumno: Optional[str] = None
    tutor_level: Optional[str] = None
    pista_numero: Optional[int] = None

class ChatResponse(BaseModel):
    respuesta: str
    dify_conversation_id: str
    status: str
    agente_nombre: Optional[str] = None

class PistonFile(BaseModel):
    name: str
    content: str

class ExecuteRequest(BaseModel):
    language: str
    version: str
    files: List[PistonFile]

class LoginRequest(BaseModel):
    usuario_id: str
    contrasena: str

class RegisterRequest(BaseModel):
    usuario_id: str
    nombre: str
    correo: str
    contrasena: str

class LoginResponse(BaseModel):
    usuario_id: str
    nombre: str
    correo: str
    rol: str
    xp: int
    nivel: int
    tema_actual: str
    porcentaje: int
    status: str
    examen_completado: bool = False

class UserUpdate(BaseModel):
    nombre: Optional[str] = None
    xp: Optional[int] = None
    nivel: Optional[int] = None
    tema_actual: Optional[str] = None
    porcentaje: Optional[int] = None

class EjercicioResponse(BaseModel):
    id: int
    titulo: str
    descripcion: str
    tema: str
    dificultad: str
    codigo_inicial_python: Optional[str] = None
    codigo_inicial_java: Optional[str] = None
    casos_prueba: Optional[str] = None
    aprobado: bool
    resuelto: bool = False
    codigo_resuelto: Optional[str] = None
    lenguaje: Optional[str] = None

    class Config:
        from_attributes = True
        orm_mode = True

class ValidateRequest(BaseModel):
    usuario_id: str
    ejercicio_id: int
    resolucion_codigo: str
    resultado_consola: str
    lenguaje: Optional[str] = None


class ProfileUpdateRequest(BaseModel):
    nombre: str
    correo: str
    contrasena: Optional[str] = None


class AnswerItem(BaseModel):
    pregunta_id: int
    respuesta: str


class ExamSubmitRequest(BaseModel):
    usuario_id: str
    respuestas: List[AnswerItem]


class GoogleAuthRequest(BaseModel):
    email: str
    name: str
    uid: str


class XPDeductRequest(BaseModel):
    usuario_id: str
    descuento_xp: int


class XPDeductResponse(BaseModel):
    xp: int
    nivel: int
    status: str

