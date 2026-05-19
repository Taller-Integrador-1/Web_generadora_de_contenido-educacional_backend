from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.config.database import engine, get_db
from app.models import models
from app.schemas.schemas import (
    ChatRequest, ChatResponse, CompileRequest, ExecuteRequest,
    LoginRequest, RegisterRequest, LoginResponse, UserUpdate
)
from fastapi.middleware.cors import CORSMiddleware
from app.services.dify_service import DifyService
from app.utils.security import hash_password, verify_password
import subprocess
import os
import tempfile
import requests

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS contrasena VARCHAR(255);"))
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS rol VARCHAR(20) DEFAULT 'student';"))
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS xp INTEGER DEFAULT 0;"))
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS nivel INTEGER DEFAULT 1;"))
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS tema_actual VARCHAR(100) DEFAULT 'Variables';"))
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS porcentaje INTEGER DEFAULT 0;"))
        conn.commit()
    print("[Migraciones] Columnas migradas o ya existentes.")
except Exception as e:
    print(f"[Migraciones] Error al ejecutar: {e}")

models.Base.metadata.create_all(bind=engine)

from app.config.database import SessionLocal
db = SessionLocal()
try:
    estudiante = db.query(models.Usuario).filter(models.Usuario.id == "UPAO-123").first()
    if not estudiante:
        estudiante = models.Usuario(
            id="UPAO-123",
            nombre="Walther Cueva",
            correo="walther@upao.edu.pe",
            contrasena=hash_password("password123"),
            rol="student",
            xp=0,
            nivel=1,
            tema_actual="Variables",
            porcentaje=0
        )
        db.add(estudiante)
        db.commit()
        print("[Seeding] Estudiante semilla creado exitosamente.")
    else:
        if not estudiante.contrasena or estudiante.contrasena == "password123":
            estudiante.contrasena = hash_password("password123")
            db.commit()

    administrador = db.query(models.Usuario).filter(models.Usuario.id == "admin").first()
    if not administrador:
        administrador = models.Usuario(
            id="admin",
            nombre="Administrador UPAO",
            correo="admin@upao.edu.pe",
            contrasena=hash_password("admin123"),
            rol="admin",
            xp=0,
            nivel=0,
            tema_actual="",
            porcentaje=0
        )
        db.add(administrador)
        db.commit()
        print("[Seeding] Administrador semilla creado exitosamente.")
    else:
        if not administrador.contrasena or administrador.contrasena == "admin123":
            administrador.contrasena = hash_password("admin123")
            db.commit()
finally:
    db.close()


app = FastAPI(title="API Tutor Socrático Algoritmia")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

dify_service = DifyService()

@app.post("/api/chat", response_model=ChatResponse)
async def procesar_chat(request: ChatRequest, db: Session = Depends(get_db)):
    try:
        resultado_dify = dify_service.enviar_mensaje(
            query=request.mensaje,
            user_id=request.usuario_id,
            conversation_id=request.dify_conversation_id
        )
        
        respuesta_juez = resultado_dify.get("answer")
        nuevo_conv_id = resultado_dify.get("conversation_id")
        
        intento_fraude = 0
        if respuesta_juez and ("Reescribe la respuesta eliminando el código" in respuesta_juez or "No puedo proporcionarte código" in respuesta_juez):
            intento_fraude = 1
            
        usuario = db.query(models.Usuario).filter(models.Usuario.id == request.usuario_id).first()
        if not usuario:
            usuario = models.Usuario(
                id=request.usuario_id,
                nombre=f"Alumno {request.usuario_id}",
                correo=f"{request.usuario_id}@upao.edu.pe"
            )
            db.add(usuario)
            db.commit()
            db.refresh(usuario)

        sesion = None
        if request.dify_conversation_id:
            sesion = db.query(models.SesionChat).filter(models.SesionChat.dify_conversation_id == request.dify_conversation_id).first()
        
        if not sesion:
            sesion = models.SesionChat(
                dify_conversation_id=nuevo_conv_id,
                usuario_id=request.usuario_id
            )
            db.add(sesion)
            db.commit()
            db.refresh(sesion)

        msg_user = models.MensajeLog(
            sesion_id=sesion.id,
            rol="user",
            contenido=request.mensaje,
            intento_codigo=0
        )
        db.add(msg_user)

        msg_ai = models.MensajeLog(
            sesion_id=sesion.id,
            rol="assistant",
            contenido=respuesta_juez,
            intento_codigo=intento_fraude
        )
        db.add(msg_ai)
        
        db.commit()

        return ChatResponse(
            respuesta=respuesta_juez,
            dify_conversation_id=nuevo_conv_id,
            status="success"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/execute")
def proxy_execute_code(request: ExecuteRequest):
    try:
        piston_url = "http://localhost:2000/api/v2/execute"
        
        payload = {
            "language": request.language,
            "version": request.version,
            "files": [{"name": f.name, "content": f.content} for f in request.files]
        }
        
        response = requests.post(piston_url, json=payload)
        
        if response.status_code == 401:
            raise HTTPException(status_code=401, detail="Piston API requiere autorización.")
            
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error conectando con el motor Piston: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/register", response_model=LoginResponse)
async def registrar_usuario(request: RegisterRequest, db: Session = Depends(get_db)):
    existe_usuario = db.query(models.Usuario).filter(models.Usuario.id == request.usuario_id).first()
    if existe_usuario:
        raise HTTPException(status_code=400, detail="El código de estudiante ya está registrado.")
    
    existe_correo = db.query(models.Usuario).filter(models.Usuario.correo == request.correo).first()
    if existe_correo:
        raise HTTPException(status_code=400, detail="El correo electrónico ya está registrado.")
    
    nuevo_usuario = models.Usuario(
        id=request.usuario_id,
        nombre=request.nombre,
        correo=request.correo,
        contrasena=hash_password(request.contrasena),
        rol="student",
        xp=0,
        nivel=1,
        tema_actual="Variables",
        porcentaje=0
    )
    try:
        db.add(nuevo_usuario)
        db.commit()
        db.refresh(nuevo_usuario)
        
        return LoginResponse(
            usuario_id=nuevo_usuario.id,
            nombre=nuevo_usuario.nombre,
            correo=nuevo_usuario.correo,
            rol=nuevo_usuario.rol,
            xp=nuevo_usuario.xp,
            nivel=nuevo_usuario.nivel,
            tema_actual=nuevo_usuario.tema_actual,
            porcentaje=nuevo_usuario.porcentaje,
            status="success"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al registrar usuario: {str(e)}")


@app.post("/api/login", response_model=LoginResponse)
async def login_usuario(request: LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).filter(models.Usuario.id == request.usuario_id).first()
    if not usuario:
        usuario = db.query(models.Usuario).filter(models.Usuario.correo == request.usuario_id).first()
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    
    if not verify_password(request.contrasena, usuario.contrasena):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta.")
    
    return LoginResponse(
        usuario_id=usuario.id,
        nombre=usuario.nombre,
        correo=usuario.correo,
        rol=usuario.rol,
        xp=usuario.xp,
        nivel=usuario.nivel,
        tema_actual=usuario.tema_actual,
        porcentaje=usuario.porcentaje,
        status="success"
    )


@app.get("/api/admin/users")
async def get_all_students(db: Session = Depends(get_db)):
    usuarios = db.query(models.Usuario).filter(models.Usuario.rol == "student").all()
    return [{
        "usuario_id": u.id,
        "nombre": u.nombre,
        "correo": u.correo,
        "rol": u.rol,
        "xp": u.xp,
        "nivel": u.nivel,
        "tema_actual": u.tema_actual,
        "porcentaje": u.porcentaje
    } for u in usuarios]


@app.put("/api/admin/users/{user_id}")
async def update_student(user_id: str, request: UserUpdate, db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).filter(models.Usuario.id == user_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    
    if request.nombre is not None:
        usuario.nombre = request.nombre
    if request.xp is not None:
        usuario.xp = request.xp
    if request.nivel is not None:
        usuario.nivel = request.nivel
    if request.tema_actual is not None:
        usuario.tema_actual = request.tema_actual
    if request.porcentaje is not None:
        usuario.porcentaje = request.porcentaje
        
    try:
        db.commit()
        db.refresh(usuario)
        return {
            "usuario_id": usuario.id,
            "nombre": usuario.nombre,
            "xp": usuario.xp,
            "nivel": usuario.nivel,
            "tema_actual": usuario.tema_actual,
            "porcentaje": usuario.porcentaje,
            "status": "success"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


