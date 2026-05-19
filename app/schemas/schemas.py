from pydantic import BaseModel
from typing import Optional, List

class ChatRequest(BaseModel):
    usuario_id: str
    mensaje: str
    dify_conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    respuesta: str
    dify_conversation_id: str
    status: str

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

class UserUpdate(BaseModel):
    nombre: Optional[str] = None
    xp: Optional[int] = None
    nivel: Optional[int] = None
    tema_actual: Optional[str] = None
    porcentaje: Optional[int] = None
