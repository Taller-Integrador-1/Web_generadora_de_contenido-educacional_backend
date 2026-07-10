from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, LargeBinary
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class Usuario(Base):
    __tablename__ = "usuarios"
    
    id = Column(String(50), primary_key=True)
    nombre = Column(String(100), nullable=False)
    correo = Column(String(100), unique=True, nullable=False)
    contrasena = Column(String(255), nullable=False)
    rol = Column(String(20), nullable=False, default="student")
    xp = Column(Integer, default=0)
    nivel = Column(Integer, default=1)
    tema_actual = Column(String(100), default="Variables")
    porcentaje = Column(Integer, default=0)
    examen_completado = Column(Boolean, default=False)
    
    sesiones = relationship("SesionChat", back_populates="usuario")

class SesionChat(Base):
    __tablename__ = "sesiones_chat"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    dify_conversation_id = Column(String(255), unique=True, nullable=True)
    usuario_id = Column(String(50), ForeignKey("usuarios.id"))
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    
    usuario = relationship("Usuario", back_populates="sesiones")
    mensajes = relationship("MensajeLog", back_populates="sesion")

class MensajeLog(Base):
    __tablename__ = "mensajes_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sesion_id = Column(Integer, ForeignKey("sesiones_chat.id"))
    rol = Column(String(20))
    contenido = Column(Text, nullable=False)
    intento_codigo = Column(Integer, default=0)
    fecha = Column(DateTime, default=datetime.utcnow)
    
    sesion = relationship("SesionChat", back_populates="mensajes")

class Ejercicio(Base):
    __tablename__ = "ejercicios"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    titulo = Column(String(150), nullable=False)
    descripcion = Column(Text, nullable=False)
    tema = Column(String(100), nullable=False)
    dificultad = Column(String(50), nullable=False, default="Media")
    codigo_inicial_python = Column(Text, nullable=True)
    codigo_inicial_java = Column(Text, nullable=True)
    casos_prueba = Column(Text, nullable=True)
    aprobado = Column(Boolean, default=False)
    resuelto = Column(Boolean, default=False)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)

class ResolucionEjercicio(Base):
    __tablename__ = "resoluciones_ejercicios"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(String(50), ForeignKey("usuarios.id"), nullable=False)
    ejercicio_id = Column(Integer, ForeignKey("ejercicios.id"), nullable=False)
    codigo_resuelto = Column(Text, nullable=True)
    lenguaje = Column(String(20), nullable=True)
    fecha_resolucion = Column(DateTime, default=datetime.utcnow)


class Silabo(Base):
    __tablename__ = "silabos"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    contenido = Column(Text, nullable=False)
    file_data = Column(LargeBinary, nullable=True)
    fecha_subida = Column(DateTime, default=datetime.utcnow)


class PreguntaExamen(Base):
    __tablename__ = "preguntas_examen"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tema = Column(String(100), nullable=False)
    pregunta = Column(Text, nullable=False)
    opcion_a = Column(String(255), nullable=False)
    opcion_b = Column(String(255), nullable=False)
    opcion_c = Column(String(255), nullable=False)
    opcion_d = Column(String(255), nullable=False)
    respuesta_correcta = Column(String(1), nullable=False)
