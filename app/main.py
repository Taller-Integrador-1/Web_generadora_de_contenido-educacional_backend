from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.config.database import engine, get_db
from app.models import models
from app.schemas.schemas import (
    ChatRequest, ChatResponse, ExecuteRequest,
    LoginRequest, RegisterRequest, LoginResponse, UserUpdate,
    EjercicioResponse, ValidateRequest, ProfileUpdateRequest
)
from fastapi.middleware.cors import CORSMiddleware
from app.services.dify_service import DifyService
from app.utils.security import hash_password, verify_password
import subprocess
import os
import tempfile
import requests
import json
import re
import dotenv
import unicodedata

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS contrasena VARCHAR(255);"))
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS rol VARCHAR(20) DEFAULT 'student';"))
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS xp INTEGER DEFAULT 0;"))
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS nivel INTEGER DEFAULT 1;"))
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS tema_actual VARCHAR(100) DEFAULT 'Variables';"))
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS porcentaje INTEGER DEFAULT 0;"))
        conn.execute(text("ALTER TABLE ejercicios ADD COLUMN IF NOT EXISTS casos_prueba TEXT;"))
        conn.execute(text("ALTER TABLE ejercicios ADD COLUMN IF NOT EXISTS resuelto BOOLEAN DEFAULT FALSE;"))
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

@app.get("/")
def read_root():
    return {
        "status": "healthy",
        "service": "API Tutor Socrático Algoritmia",
        "message": "Servidor activo. Accede a /docs para ver la documentación de la API."
    }

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
    import subprocess
    import tempfile
    import os

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            main_file = None
            
            for f in request.files:
                file_path = os.path.join(temp_dir, f.name)
                with open(file_path, "w", encoding="utf-8") as out:
                    out.write(f.content)
                if f.name.endswith(".py") or f.name == "Main.java":
                    main_file = f.name
            
            if not main_file:
                return {"compile": {"stderr": "No se encontró el archivo principal (.py o Main.java)"}, "run": {"code": 1}}

            if request.language == "python":
                try:
                    result = subprocess.run(
                        ["python3", main_file], 
                        cwd=temp_dir, capture_output=True, text=True, timeout=5
                    )
                    return {
                        "run": {
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                            "code": result.returncode,
                            "signal": None
                        }
                    }
                except subprocess.TimeoutExpired:
                    return {"run": {"stdout": "", "stderr": "Error: Tiempo límite de ejecución excedido (5s).", "code": 1}}
            
            elif request.language == "java":
                try:
                    compile_result = subprocess.run(
                        ["javac", main_file], 
                        cwd=temp_dir, capture_output=True, text=True, timeout=5
                    )
                    if compile_result.returncode != 0:
                        return {"compile": {"stderr": compile_result.stderr}, "run": {"code": 1}}
                    
                    class_name = main_file.replace(".java", "")
                    result = subprocess.run(
                        ["java", class_name], 
                        cwd=temp_dir, capture_output=True, text=True, timeout=5
                    )
                    return {
                        "run": {
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                            "code": result.returncode,
                            "signal": None
                        }
                    }
                except subprocess.TimeoutExpired:
                    return {"run": {"stdout": "", "stderr": "Error: Tiempo límite de ejecución excedido (5s).", "code": 1}}
            
            else:
                return {"compile": {"stderr": f"Lenguaje no soportado: {request.language}"}, "run": {"code": 1}}

    except Exception as e:
        return {"compile": {"stderr": f"Error interno del servidor: {str(e)}"}, "run": {"code": 1}}


def check_and_advance_empty_topics(usuario: models.Usuario, db: Session):
    all_topics = ["Variables", "Tipos de Datos", "Operadores", "Condicionales", "Bucles For", "Bucles While", "Funciones", "Arrays", "Objetos"]
    
    if not usuario.tema_actual or usuario.tema_actual not in all_topics:
        usuario.tema_actual = "Variables"
        
    while True:
        current_theme = usuario.tema_actual
        try:
            idx = all_topics.index(current_theme)
        except ValueError:
            idx = 0
            
        num_ejercicios = db.query(models.Ejercicio).filter(
            models.Ejercicio.aprobado == True,
            models.Ejercicio.tema.ilike(all_topics[idx])
        ).count()
        
        if num_ejercicios == 0:
            next_topic = None
            for t in all_topics[idx + 1:]:
                c = db.query(models.Ejercicio).filter(
                    models.Ejercicio.aprobado == True,
                    models.Ejercicio.tema.ilike(t)
                ).count()
                if c > 0:
                    next_topic = t
                    break
            
            if next_topic:
                usuario.tema_actual = next_topic
                usuario.porcentaje = 0
                continue
            else:
                break
        else:
            num_resueltos = db.query(models.Ejercicio).filter(
                models.Ejercicio.aprobado == True,
                models.Ejercicio.tema.ilike(all_topics[idx]),
                models.Ejercicio.resuelto == True
            ).count()
            
            if num_resueltos >= num_ejercicios:
                next_topic = None
                for t in all_topics[idx + 1:]:
                    c = db.query(models.Ejercicio).filter(
                        models.Ejercicio.aprobado == True,
                        models.Ejercicio.tema.ilike(t)
                    ).count()
                    if c > 0:
                        next_topic = t
                        break
                
                if next_topic:
                    usuario.tema_actual = next_topic
                    usuario.porcentaje = 0
                    continue
                else:
                    usuario.porcentaje = num_resueltos
                    break
            else:
                usuario.porcentaje = num_resueltos
                break
                
    db.commit()


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
    
    check_and_advance_empty_topics(usuario, db)
    
    return LoginResponse(
        usuario_id=usuario.id,
        nombre=usuario.nombre,
        correo=usuario.correo,
        rol=usuario.rol or "student",
        xp=usuario.xp or 0,
        nivel=usuario.nivel or 1,
        tema_actual=usuario.tema_actual or "Variables",
        porcentaje=usuario.porcentaje or 0,
        status="success"
    )


@app.get("/api/chat/history/{usuario_id}")
async def obtener_historial_chat(usuario_id: str, db: Session = Depends(get_db)):
    sesion = db.query(models.SesionChat)\
        .filter(models.SesionChat.usuario_id == usuario_id)\
        .order_by(models.SesionChat.fecha_creacion.desc())\
        .first()
    
    if not sesion:
        return {"dify_conversation_id": None, "mensajes": []}
    
    mensajes = db.query(models.MensajeLog)\
        .filter(models.MensajeLog.sesion_id == sesion.id)\
        .order_by(models.MensajeLog.fecha.asc())\
        .all()
        
    return {
        "dify_conversation_id": sesion.dify_conversation_id,
        "mensajes": [
            {
                "rol": m.rol,
                "contenido": m.contenido,
                "fecha": m.fecha.isoformat() if m.fecha else None
            } for m in mensajes
        ]
    }


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


def extract_text_from_file(file_content: bytes, filename: str) -> str:
    import io
    text = ""
    if filename.endswith(".pdf"):
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_content))
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
        except Exception as e:
            print(f"Error extrayendo texto del PDF: {e}")
    elif filename.endswith(".docx"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(file_content))
            text = "\n".join([p.text for p in doc.paragraphs])
        except Exception as e:
            print(f"Error extrayendo texto del DOCX: {e}")
    return text

def clean_name(name: str) -> str:
    name = "".join(
        c for c in unicodedata.normalize('NFD', name)
        if unicodedata.category(c) != 'Mn'
    )
    name = re.sub(r'[^a-zA-Z0-9\s_]', '', name)
    name = re.sub(r'[\s_]+', '_', name).strip('_').lower()
    return name


def generate_initial_codes(titulo: str, casos_prueba) -> tuple:
    func_name = clean_name(titulo)
    if not func_name:
        func_name = "mi_funcion"
        
    params = []
    if isinstance(casos_prueba, list) and len(casos_prueba) > 0:
        first_case = casos_prueba[0]
        inp = first_case.get("input")
        if isinstance(inp, dict):
            params = [clean_name(k) for k in inp.keys()]
        elif isinstance(inp, list):
            params = [f"arg{i+1}" for i in range(len(inp))]
            
    if not params:
        params = ["valor"]
        
    py_params = ", ".join(params)
    py_code = f"def {func_name}({py_params}):\n    # Escribe tu código aquí\n    pass\n"
    
    java_params_list = []
    if isinstance(casos_prueba, list) and len(casos_prueba) > 0:
        first_case = casos_prueba[0]
        inp = first_case.get("input")
        if isinstance(inp, dict):
            for k, v in inp.items():
                p_name = clean_name(k)
                if isinstance(v, bool):
                    p_type = "boolean"
                elif isinstance(v, int):
                    p_type = "int"
                elif isinstance(v, float):
                    p_type = "double"
                elif isinstance(v, list):
                    if len(v) > 0 and isinstance(v[0], int):
                        p_type = "int[]"
                    elif len(v) > 0 and isinstance(v[0], float):
                        p_type = "double[]"
                    else:
                        p_type = "List<Object>"
                else:
                    p_type = "String"
                java_params_list.append(f"{p_type} {p_name}")
        elif isinstance(inp, list):
            for i, v in enumerate(inp):
                p_name = f"arg{i+1}"
                if isinstance(v, bool):
                    p_type = "boolean"
                elif isinstance(v, int):
                    p_type = "int"
                elif isinstance(v, float):
                    p_type = "double"
                elif isinstance(v, list):
                    if len(v) > 0 and isinstance(v[0], int):
                        p_type = "int[]"
                    elif len(v) > 0 and isinstance(v[0], float):
                        p_type = "double[]"
                    elif len(v) > 0 and isinstance(v[0], str):
                        p_type = "String[]"
                    else:
                        p_type = "List<Object>"
                else:
                    p_type = "String"
                java_params_list.append(f"{p_type} {p_name}")
                
    if not java_params_list:
        java_params_list = ["String valor"]
        
    java_params = ", ".join(java_params_list)
    
    ret_type = "void"
    if isinstance(casos_prueba, list) and len(casos_prueba) > 0:
        out_val = casos_prueba[0].get("output")
        if isinstance(out_val, bool):
            ret_type = "boolean"
        elif isinstance(out_val, int):
            ret_type = "int"
        elif isinstance(out_val, float):
            ret_type = "double"
        elif isinstance(out_val, list):
            if len(out_val) > 0 and isinstance(out_val[0], int):
                ret_type = "int[]"
            else:
                ret_type = "List<Object>"
        elif out_val is not None:
            ret_type = "String"
            
    java_func_name = ""
    parts = func_name.split("_")
    if len(parts) > 0:
        java_func_name = parts[0] + "".join(p.capitalize() for p in parts[1:])
    else:
        java_func_name = "miFuncion"
        
    if ret_type == "void":
        java_code = f"public class Main {{\n    public static void {java_func_name}({java_params}) {{\n        // Escribe tu código aquí\n    }}\n}}"
    elif ret_type == "boolean":
        java_code = f"public class Main {{\n    public static boolean {java_func_name}({java_params}) {{\n        // Escribe tu código aquí\n        return false;\n    }}\n}}"
    elif ret_type == "int":
        java_code = f"public class Main {{\n    public static int {java_func_name}({java_params}) {{\n        // Escribe tu código aquí\n        return 0;\n    }}\n}}"
    elif ret_type == "double":
        java_code = f"public class Main {{\n    public static double {java_func_name}({java_params}) {{\n        // Escribe tu código aquí\n        return 0.0;\n    }}\n}}"
    elif ret_type == "String":
        java_code = f"public class Main {{\n    public static String {java_func_name}({java_params}) {{\n        // Escribe tu código aquí\n        return \"\";\n    }}\n}}"
    else:
        java_code = f"import java.util.*;\n\npublic class Main {{\n    public static {ret_type} {java_func_name}({java_params}) {{\n        // Escribe tu código aquí\n        return null;\n    }}\n}}"

    return py_code, java_code


def categorize_exercise(titulo: str, descripcion: str) -> str:
    text = f"{titulo} {descripcion}".lower()
    if any(w in text for w in ["arreglo", "lista", "matriz", "vectores", "vector", "colección", "coleccion", "listas", "arrays", "array"]):
        return "Arrays"
    if any(w in text for w in ["objeto", "clase", "class", "instancia", "propiedad", "atributos", "orientado a objetos", "poo"]):
        return "Objetos"
    if "while" in text or "mientras" in text or "hasta que" in text:
        return "Bucles While"
    if any(w in text for w in ["bucle for", "ciclo for", "para cada", "secuencia de fibonacci", "fibonacci", "factorial"]):
        return "Bucles For"
    if any(w in text for w in ["bucle", "ciclo", "repetir", "iterar", "rango", "tabla de multiplicar", "pares en un rango"]):
        return "Bucles For"
    if any(w in text for w in ["condición", "condicion", "si es", "es mayor", "es menor", "edad para", "verificar si", "validar", "contraseña", "contrasena"]):
        return "Condicionales"
    if any(w in text for w in ["función", "funcion", "retorne", "parámetro", "def ", "retorna"]):
        return "Funciones"
    if any(w in text for w in ["operador", "suma", "resta", "multiplicación", "multiplicacion", "división", "division", "módulo", "modulo", "calcular", "área", "area", "perímetro", "perimetro", "descuento", "porcentaje", "promedio"]):
        return "Operadores"
    if any(w in text for w in ["tipo de dato", "entero", "flotante", "cadena", "string", "booleano", "convertir", "parsear", "texto"]):
        return "Tipos de Datos"
    return "Variables"


def parse_exercises_json(text_content: str) -> list:
    text_content = text_content.strip()
    if not text_content:
        return []
    
    if "```" in text_content:
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text_content)
        if match:
            text_content = match.group(1).strip()
            
    try:
        parsed = json.loads(text_content)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            if "ejercicios" in parsed:
                return parsed["ejercicios"]
            return [parsed]
    except Exception:
        pass
        
    try:
        array_match = re.search(r'(\[[\s\S]*\])', text_content)
        if array_match:
            parsed = json.loads(array_match.group(1))
            if isinstance(parsed, list):
                return parsed
    except Exception:
        pass
        
    try:
        dict_match = re.search(r'(\{[\s\S]*\})', text_content)
        if dict_match:
            parsed = json.loads(dict_match.group(1))
            if isinstance(parsed, dict):
                if "ejercicios" in parsed:
                    return parsed["ejercicios"]
                return [parsed]
    except Exception:
        pass
        
    return []


@app.post("/api/admin/upload-syllabus")
async def upload_syllabus(
    file: UploadFile = File(...),
    cantidad: int = Form(3),
    db: Session = Depends(get_db)
):
    try:
        dotenv.load_dotenv(override=True)
        
        file_content = await file.read()
        extracted_text = extract_text_from_file(file_content, file.filename)
        
        ejercicios_list = []
        
        DIFY_API_KEY_DATASET = os.getenv("DIFY_API_KEY_DATASET")
        DIFY_DATASET_ID = os.getenv("DIFY_DATASET_ID")
        DIFY_API_KEY_GENERATOR = os.getenv("DIFY_API_KEY_GENERATOR")
        
        if DIFY_API_KEY_DATASET and DIFY_DATASET_ID and "placeholder" not in DIFY_API_KEY_DATASET:
            try:
                dataset_upload_url = f"https://api.dify.ai/v1/datasets/{DIFY_DATASET_ID}/document/create-by-file"
                headers = {
                    "Authorization": f"Bearer {DIFY_API_KEY_DATASET}"
                }
                files = {
                    "file": (file.filename, file_content, file.content_type or "application/octet-stream")
                }
                data = {
                    "data": json.dumps({
                        "indexing_technique": "high_quality",
                        "process_rule": {
                            "mode": "automatic"
                        }
                    })
                }
                print(f"[Dify Dataset] Subiendo archivo a dataset {DIFY_DATASET_ID}...")
                ds_response = requests.post(dataset_upload_url, headers=headers, files=files, data=data, timeout=20)
                ds_response.raise_for_status()
                print("[Dify Dataset] Documento subido y indexado exitosamente.")
            except Exception as ds_err:
                print(f"[Dify Dataset] Error al subir documento: {ds_err}")
        else:
            print("[Dify Dataset] API Key o Dataset ID faltante o placeholder. Saltando subida de dataset.")

        if DIFY_API_KEY_GENERATOR and "placeholder" not in DIFY_API_KEY_GENERATOR:
            try:
                workflow_run_url = "https://api.dify.ai/v1/workflows/run"
                headers = {
                    "Authorization": f"Bearer {DIFY_API_KEY_GENERATOR}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "inputs": {
                        "cantidad": int(cantidad),
                        "texto_silabo_actual": extracted_text
                    },
                    "response_mode": "blocking",
                    "user": "admin"
                }
                print("[Dify Workflow Generator] Ejecutando workflow generador de retos...")
                wf_response = requests.post(workflow_run_url, headers=headers, json=payload, timeout=40)
                wf_response.raise_for_status()
                wf_data = wf_response.json()
                
                outputs = wf_data.get("data", {}).get("outputs", {}) or wf_data.get("outputs", {})
                
                ejercicios_list = []
                
                ejercicios_raw = outputs.get("ejercicios_generados")
                if ejercicios_raw:
                    if isinstance(ejercicios_raw, list):
                        ejercicios_list = ejercicios_raw
                    elif isinstance(ejercicios_raw, str):
                        ejercicios_list = parse_exercises_json(ejercicios_raw)
                        
                if not ejercicios_list:
                    answer = ""
                    for key in ["text", "result", "textString", "output", "string", "response", "ejercicios"]:
                        if key in outputs:
                            val = outputs[key]
                            if isinstance(val, list):
                                ejercicios_list = val
                                break
                            elif isinstance(val, str):
                                answer = val
                                break
                    if not ejercicios_list and not answer:
                        for k, v in outputs.items():
                            if isinstance(v, list):
                                ejercicios_list = v
                                break
                            elif isinstance(v, str) and v:
                                answer = v
                                break
                    if answer and not ejercicios_list:
                        ejercicios_list = parse_exercises_json(answer)
                        
                if ejercicios_list:
                    print(f"[Dify Workflow Generator] Se obtuvieron {len(ejercicios_list)} ejercicios desde Dify.")
            except Exception as wf_err:
                print(f"[Dify Workflow Generator] Error al ejecutar workflow: {wf_err}")
        else:
            print("[Dify Workflow Generator] API Key de generador faltante o placeholder. Usando fallback.")

        if not ejercicios_list:
            raise HTTPException(
                status_code=400,
                detail="El agente de Dify no pudo generar los retos a partir del sílabo. Por favor, asegúrate de haber publicado tu workflow 'ejercicios_ed_tech' en la interfaz de Dify."
            )
            
        created_ejercicios = []
        for ej in ejercicios_list:
            titulo = ej.get("titulo", "Reto Generado")
            descripcion = ej.get("descripcion", "Descripción del ejercicio.")
            
            diff_raw = ej.get("dificultad", "medio")
            if not isinstance(diff_raw, str):
                diff_raw = "medio"
            diff_raw = diff_raw.lower()
            if "facil" in diff_raw or "fácil" in diff_raw:
                dificultad = "Fácil"
            elif "dificil" in diff_raw or "difícil" in diff_raw:
                dificultad = "Difícil"
            else:
                dificultad = "Media"
                
            tema = ej.get("tema")
            if not tema or tema not in ["Variables", "Tipos de Datos", "Operadores", "Condicionales", "Bucles For", "Bucles While", "Funciones", "Arrays", "Objetos"]:
                tema = categorize_exercise(titulo, descripcion)
                
            casos_prueba_raw = ej.get("casos_prueba", "Ejecutar y validar la salida del programa.")
            if isinstance(casos_prueba_raw, (list, dict)):
                casos_prueba = json.dumps(casos_prueba_raw, ensure_ascii=False)
            else:
                casos_prueba = str(casos_prueba_raw)
                
            py_code = ej.get("codigo_inicial_python", "")
            java_code = ej.get("codigo_inicial_java", "")
            if not py_code or not java_code:
                gen_py, gen_java = generate_initial_codes(titulo, casos_prueba_raw)
                if not py_code:
                    py_code = gen_py
                if not java_code:
                    java_code = gen_java
            
            nuevo_ej = models.Ejercicio(
                titulo=titulo,
                descripcion=descripcion,
                tema=tema,
                dificultad=dificultad,
                codigo_inicial_python=py_code,
                codigo_inicial_java=java_code,
                casos_prueba=casos_prueba,
                aprobado=False
            )
            db.add(nuevo_ej)
            created_ejercicios.append(nuevo_ej)
            
        db.commit()
        for ej in created_ejercicios:
            db.refresh(ej)
            
        return created_ejercicios
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/exercises/validate")
async def validate_exercise(request: ValidateRequest, db: Session = Depends(get_db)):
    try:
        dotenv.load_dotenv(override=True)
        
        ejercicio = db.query(models.Ejercicio).filter(models.Ejercicio.id == request.ejercicio_id).first()
        if not ejercicio:
            raise HTTPException(status_code=404, detail="Ejercicio no encontrado")
            
        DIFY_API_KEY_VALIDATOR = os.getenv("DIFY_API_KEY_VALIDATOR")
        
        feedback = "Error de conexión con el validador de Dify."
        is_correct = False
        
        if DIFY_API_KEY_VALIDATOR and "placeholder" not in DIFY_API_KEY_VALIDATOR:
            try:
                workflow_run_url = "https://api.dify.ai/v1/workflows/run"
                headers = {
                    "Authorization": f"Bearer {DIFY_API_KEY_VALIDATOR}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "inputs": {
                        "descripcion_ejercicio": ejercicio.descripcion,
                        "casos_prueba": ejercicio.casos_prueba or "Validar que la salida sea correcta.",
                        "codigo_alumno": request.resolucion_codigo,
                        "salida_compilador": request.resultado_consola
                    },
                    "response_mode": "blocking",
                    "user": request.usuario_id
                }
                print(f"[Dify Validator] Enviando código de {request.usuario_id} al workflow validador...")
                wf_response = requests.post(workflow_run_url, headers=headers, json=payload, timeout=30)
                wf_response.raise_for_status()
                wf_data = wf_response.json()
                
                outputs = wf_data.get("data", {}).get("outputs", {}) or wf_data.get("outputs", {})
                
                aprobado_val = outputs.get("aprobado")
                feedback_val = outputs.get("feedback")
                
                if aprobado_val is None or feedback_val is None:
                    for val in outputs.values():
                        if isinstance(val, str):
                            cleaned_val = val.strip()
                            if "```" in cleaned_val:
                                match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", cleaned_val)
                                if match:
                                    cleaned_val = match.group(1).strip()
                            if cleaned_val.startswith("{"):
                                try:
                                    parsed_val = json.loads(cleaned_val)
                                    if isinstance(parsed_val, dict):
                                        if "aprobado" in parsed_val:
                                            aprobado_val = parsed_val["aprobado"]
                                        if "feedback" in parsed_val:
                                            feedback_val = parsed_val["feedback"]
                                        break
                                except Exception:
                                    pass
                                
                if feedback_val:
                    feedback = str(feedback_val)
                else:
                    for key in ["text", "result", "textString", "output", "string", "response"]:
                        if key in outputs:
                            feedback = outputs[key]
                            break
                    if not feedback or feedback == "Error de conexión con el validador de Dify.":
                        for k, v in outputs.items():
                            if isinstance(v, str) and v:
                                feedback = v
                                break
                    
                if aprobado_val is not None:
                    if isinstance(aprobado_val, bool):
                        is_correct = aprobado_val
                    elif isinstance(aprobado_val, str):
                        is_correct = aprobado_val.lower() in ["true", "1", "sí", "si", "correcto", "approved", "ok"]
                else:
                    feedback_lower = feedback.lower()
                    if "incorrecto" in feedback_lower or "incorrecta" in feedback_lower or "falla" in feedback_lower or "error" in feedback_lower:
                        is_correct = False
                    elif "correcto" in feedback_lower or "correcta" in feedback_lower or "aprobado" in feedback_lower or "superado" in feedback_lower:
                        is_correct = True
                    else:
                        is_correct = False
            except Exception as wf_err:
                print(f"[Dify Validator] Error al ejecutar workflow: {wf_err}")
                feedback = f"Error al ejecutar el validador Dify: {str(wf_err)}"
                
        if not DIFY_API_KEY_VALIDATOR or "placeholder" in DIFY_API_KEY_VALIDATOR or not feedback or "Error" in feedback:
            print("[Dify Validator] Usando evaluación de fallback heurístico...")
            if request.resultado_consola and "error" not in request.resultado_consola.lower() and "exception" not in request.resultado_consola.lower():
                is_correct = True
                feedback = (
                    "¡Excelente! Tu código se ha ejecutado correctamente y la salida parece válida.\n\n"
                    "Retroalimentación (Heurística):\n"
                    "- El código no presenta errores de sintaxis.\n"
                    "- La salida de consola no contiene excepciones.\n"
                    "Resultado: CORRECTO"
                )
            else:
                is_correct = False
                feedback = (
                    "Tu código se ejecutó pero la consola muestra errores o está vacía. Revisa tu solución.\n\n"
                    "Resultado: INCORRECTO"
                )

        usuario = db.query(models.Usuario).filter(models.Usuario.id == request.usuario_id).first()
        if is_correct and usuario:
            check_and_advance_empty_topics(usuario, db)
            
            # Calcular XP según la dificultad del ejercicio
            xp_ganado = 100
            if ejercicio.dificultad:
                diff_lower = ejercicio.dificultad.lower()
                if "fácil" in diff_lower or "facil" in diff_lower:
                    xp_ganado = 100
                elif "media" in diff_lower or "medio" in diff_lower:
                    xp_ganado = 300
                elif "difícil" in diff_lower or "dificil" in diff_lower:
                    xp_ganado = 500
            
            usuario.xp += xp_ganado
            nuevo_nivel = (usuario.xp // 1000) + 1
            if nuevo_nivel != usuario.nivel:
                usuario.nivel = nuevo_nivel
            
            ejercicio.resuelto = True
            
            if ejercicio.tema.lower() == usuario.tema_actual.lower():
                num_ejercicios = db.query(models.Ejercicio).filter(
                    models.Ejercicio.aprobado == True,
                    models.Ejercicio.tema.ilike(usuario.tema_actual)
                ).count()
                
                num_resueltos = db.query(models.Ejercicio).filter(
                    models.Ejercicio.aprobado == True,
                    models.Ejercicio.tema.ilike(usuario.tema_actual),
                    models.Ejercicio.resuelto == True
                ).count()
                
                if num_ejercicios == 0:
                    num_ejercicios = 3 
                    
                usuario.porcentaje = num_resueltos
                if usuario.porcentaje >= num_ejercicios:
                    usuario.porcentaje = 0
                    all_topics = ["Variables", "Tipos de Datos", "Operadores", "Condicionales", "Bucles For", "Bucles While", "Funciones", "Arrays", "Objetos"]
                    try:
                        idx = all_topics.index(usuario.tema_actual)
                        if idx < len(all_topics) - 1:
                            usuario.tema_actual = all_topics[idx + 1]
                            check_and_advance_empty_topics(usuario, db)
                    except ValueError:
                        usuario.tema_actual = "Variables"
                        
            db.commit()
            db.refresh(usuario)
            
        user_stats = None
        if usuario:
            user_stats = {
                "xp": usuario.xp,
                "nivel": usuario.nivel,
                "tema_actual": usuario.tema_actual,
                "porcentaje": usuario.porcentaje
            }
            
        return {
            "is_correct": is_correct,
            "feedback": feedback,
            "user_stats": user_stats
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/exercises/pending")
def get_pending_exercises(db: Session = Depends(get_db)):
    return db.query(models.Ejercicio).filter(models.Ejercicio.aprobado == False).all()


@app.put("/api/admin/exercises/{id}/approve")
def approve_exercise(id: int, db: Session = Depends(get_db)):
    ej = db.query(models.Ejercicio).filter(models.Ejercicio.id == id).first()
    if not ej:
        raise HTTPException(status_code=404, detail="Ejercicio no encontrado")
    ej.aprobado = True
    db.commit()
    db.refresh(ej)
    return {"status": "success", "id": id}


@app.delete("/api/admin/exercises/{id}")
def delete_exercise(id: int, db: Session = Depends(get_db)):
    ej = db.query(models.Ejercicio).filter(models.Ejercicio.id == id).first()
    if not ej:
        raise HTTPException(status_code=404, detail="Ejercicio no encontrado")
    db.delete(ej)
    db.commit()
    return {"status": "success", "id": id}


@app.get("/api/exercises/{tema}")
def get_approved_exercises_by_topic(tema: str, db: Session = Depends(get_db)):
    return db.query(models.Ejercicio).filter(
        models.Ejercicio.aprobado == True,
        models.Ejercicio.tema.ilike(tema)
    ).all()


@app.get("/api/exercises-counts")
def get_exercise_counts(db: Session = Depends(get_db)):
    from sqlalchemy import func
    results = db.query(
        models.Ejercicio.tema, 
        func.count(models.Ejercicio.id)
    ).filter(models.Ejercicio.aprobado == True).group_by(models.Ejercicio.tema).all()
    
    return {r[0]: r[1] for r in results}


@app.get("/api/users/{usuario_id}")
def get_user_stats(usuario_id: str, db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    check_and_advance_empty_topics(usuario, db)
    
    return {
        "usuario_id": usuario.id,
        "nombre": usuario.nombre,
        "correo": usuario.correo,
        "rol": usuario.rol or "student",
        "xp": usuario.xp or 0,
        "nivel": usuario.nivel or 1,
        "tema_actual": usuario.tema_actual or "Variables",
        "porcentaje": usuario.porcentaje or 0
    }


@app.get("/api/users/{usuario_id}/progress")
def get_user_detailed_progress(usuario_id: str, db: Session = Depends(get_db)):
    from sqlalchemy import func
    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
    totales = db.query(
        models.Ejercicio.tema, 
        func.count(models.Ejercicio.id)
    ).filter(models.Ejercicio.aprobado == True).group_by(models.Ejercicio.tema).all()
    
    resueltos = db.query(
        models.Ejercicio.tema, 
        func.count(models.Ejercicio.id)
    ).filter(
        models.Ejercicio.aprobado == True,
        models.Ejercicio.resuelto == True
    ).group_by(models.Ejercicio.tema).all()
    
    totales_dict = {t[0]: t[1] for t in totales}
    resueltos_dict = {r[0]: r[1] for r in resueltos}
    
    all_topics = ["Variables", "Tipos de Datos", "Operadores", "Condicionales", "Bucles For", "Bucles While", "Funciones", "Arrays", "Objetos"]
    
    progress_data = []
    for topic in all_topics:
        t_count = totales_dict.get(topic, 0)
        r_count = resueltos_dict.get(topic, 0)
        progress_data.append({
            "topic": topic,
            "total": t_count,
            "resolved": r_count
        })
        
    return progress_data


@app.put("/api/users/{usuario_id}/profile")
def update_user_profile(usuario_id: str, request: ProfileUpdateRequest, db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if request.correo != usuario.correo:
        existe_correo = db.query(models.Usuario).filter(models.Usuario.correo == request.correo).first()
        if existe_correo:
            raise HTTPException(status_code=400, detail="El correo electrónico ya está en uso.")
    
    usuario.nombre = request.nombre
    usuario.correo = request.correo
    if request.contrasena and request.contrasena.strip() != "":
        usuario.contrasena = hash_password(request.contrasena)
        
    db.commit()
    db.refresh(usuario)
    
    return {
        "status": "success",
        "usuario": {
            "usuario_id": usuario.id,
            "nombre": usuario.nombre,
            "correo": usuario.correo,
            "rol": usuario.rol or "student",
            "xp": usuario.xp or 0,
            "nivel": usuario.nivel or 1,
            "tema_actual": usuario.tema_actual or "Variables",
            "porcentaje": usuario.porcentaje or 0
        }
    }



