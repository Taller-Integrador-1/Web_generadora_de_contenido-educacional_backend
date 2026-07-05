import os
import re
import unicodedata
import requests
import json
from typing import List, Dict, Any, TypedDict, Annotated, Optional
import google.generativeai as genai
from langgraph.graph import StateGraph, END

class AgentState(TypedDict):
    messages: List[Dict[str, str]]
    usuario_id: str
    code: str
    exercise_title: str
    exercise_desc: str
    pista_numero: Optional[int]
    technical_analysis: str
    pedagogical_context: str
    final_response: str
    next_agent: str
    active_agent: str

def get_gemini_model(system_instruction: str = None):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Falta la API Key de Gemini (GEMINI_API_KEY) en el archivo .env")
    genai.configure(api_key=api_key)
    model_name = "gemini-2.5-flash"
    return genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_instruction
    )

def query_llm(system_instruction: str, prompt: str) -> str:
    try:
        model = get_gemini_model(system_instruction=system_instruction)
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as gemini_error:
        print(f"[LLM Warning] Error en Gemini principal. Usando OpenRouter de respaldo. Detalle: {gemini_error}")
        try:
            openrouter_key = os.getenv("OPENROUTER_API_KEY")
            if not openrouter_key:
                raise ValueError("Falta la variable de entorno OPENROUTER_API_KEY en el archivo .env")
            openrouter_model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite-preview-09-2025")
            
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "EdTech Java Tutor"
            }
            
            payload = {
                "model": openrouter_model,
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ]
            }
            
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            resp.raise_for_status()
            
            data = resp.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"].strip()
            else:
                raise ValueError(f"Respuesta inesperada de OpenRouter: {data}")
        except Exception as openrouter_error:
            print(f"[LLM Error] Error crítico en OpenRouter. Detalle: {openrouter_error}")
            raise RuntimeError(f"Ambos servicios de LLM fallaron. Gemini: {gemini_error}. OpenRouter: {openrouter_error}")

def normalize_filename(filename: str) -> str:
    if not filename:
        return ""
    base_name = os.path.splitext(filename)[0]
    nfkd_form = unicodedata.normalize('NFKD', base_name)
    only_ascii = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    clean = re.sub(r'[^a-zA-Z0-9]', '', only_ascii).lower()
    return clean

def router_node(state: AgentState) -> Dict[str, Any]:
    pista_numero = state.get("pista_numero")
    if pista_numero:
        return {"next_agent": "tecnico"}

    messages = state.get("messages", [])
    last_message = messages[-1]["content"] if messages else ""
    
    prompt = f"""
    Historial del Chat:
    {messages[:-1]}
    
    Reto Activo: {state.get('exercise_title', 'Sin reto activo')}
    Descripción del Reto: {state.get('exercise_desc', '')}
    
    Código actual del alumno en el editor:
    {state.get('code', '')}
    
    Última pregunta/comentario del Alumno: "{last_message}"
    """
    system_instruction = (
        "Eres el Router de un sistema de tutoría inteligente en Java. Tu objetivo es clasificar el último mensaje del alumno.\n"
        "Debes responder ÚNICAMENTE con una de las siguientes palabras clave en minúsculas (sin puntos ni comentarios adicionales):\n"
        "- 'tecnico': Si el alumno reporta un error de compilación o de ejecución, si dice que algo no compila, si copia y pega un mensaje de error, si pregunta por qué falla su código, si muestra un error de consola, o si está reportando un bug o fallo en su programa, INCLUSO si su mensaje empieza con un saludo o comentarios en lenguaje natural (ej. 'hola, me salió este error...').\n"
        "- 'pedagogico': Si el alumno pregunta por conceptos teóricos puros (ej. qué es una variable, cómo funciona un bucle while, qué es recursividad) o temas del sílabo del curso, sin referirse a corregir un error en su código actual.\n"
        "- 'general': Si es un saludo, despedida, agradecimiento, pregunta de ayuda general sobre cómo usar la interfaz del chat, o si pide una pista socrática general para avanzar."
    )
    
    try:
        decision = query_llm(system_instruction, prompt).lower()
        
        if "tecnico" in decision:
            next_agent = "tecnico"
        elif "pedagogico" in decision:
            next_agent = "pedagogico"
        else:
            next_agent = "general"
    except Exception as e:
        print(f"[Router Node Error] {e}")
        next_agent = "general"
        
    return {"next_agent": next_agent}

def technical_node(state: AgentState) -> Dict[str, Any]:
    messages = state.get("messages", [])
    last_message = messages[-1]["content"] if messages else ""
    pista_numero = state.get("pista_numero")

    if not pista_numero:
        match = re.search(r"pista\s+#?(\d+)", last_message.lower())
        if match:
            pista_numero = int(match.group(1))

    if pista_numero:
        prompt = f"""
        El alumno ha solicitado la **Pista #{pista_numero}** para el siguiente reto de programación:
        Título del Reto: {state.get("exercise_title", "Reto activo")}
        Descripción del Reto: {state.get("exercise_desc", "Sin descripción")}
        Código actual del alumno:
        ```
        {state.get("code", "")}
        ```
        
        INSTRUCCIONES DE GENERACIÓN DE PISTAS CON CÓDIGO DEL RETO (Agente Técnico):
        - Si es la **Pista 1**: Debes darle una pequeña porción de código del ejercicio real (aproximadamente un 25% de la solución, como la firma del método o la declaración de variables iniciales) para ayudarle a empezar. Explica brevemente esta porción.
        - Si es la **Pista 2**: Debes darle una porción de código del ejercicio real más avanzada (aproximadamente un 50%-75% de la solución, como el encabezado de los bucles o la estructura de control de flujo), dejando sólo el paso/lógica final para que el alumno lo complete por sí mismo.
        - Si es la **Pista 3** o superior (donde el costo es de 100 XP): Debes proporcionarle el **CÓDIGO COMPLETO CORRECTO Y TOTALMENTE RESUELTO** para este reto actual de programación.
        
        Por favor, genera la respuesta adecuada según el número de pista ({pista_numero}).
        """
        
        system_instruction = (
            "Eres el Agente Técnico de Java. Tu tarea es asistir al alumno proporcionando la porción de código correcta "
            f"según el nivel de pista solicitado (Pista #{pista_numero}).\n"
            "Excepción a las reglas generales: En esta solicitud de pista, SÍ tienes permiso explícito para proporcionar fragmentos del código del reto "
            "o el código completo si es la pista 3 (100 XP). Explica la estructura de manera clara."
        )
    else:
        prompt = f"""
        Reto Activo: {state.get('exercise_title', 'Sin reto activo')}
        Descripción: {state.get('exercise_desc', '')}
        
        Código del Alumno:
        {state.get('code', '')}
        
        Mensaje/Error del Alumno: "{last_message}"
        """
        
        system_instruction = (
            "Eres el Agente Técnico de Java. Tu tarea es analizar el código del estudiante frente a su error reportado.\n"
            "Debes responder de forma clara y directa al alumno, explaining el diagnóstico técnico (línea exacta del error, qué falla y por qué).\n"
            "REGLA CRÍTICA DE NO FILTRADO DE CÓDIGO DIRECTO: NUNCA entregues el código de solución corregido completo para el reto actual del alumno.\n"
            "Tampoco le muestres la línea de código exacta del alumno corregida directamente. En su lugar, debes explicar el error conceptual y técnicamente, y proporcionar ejemplos de código correctos en un contexto completamente diferente (usando otros nombres de variables, clases y lógica) para ilustrar cómo solucionar el patrón del error. El alumno debe transferir este conocimiento a su propio código.\n"
            "Mantén un tono profesional, experto y de ayuda de ingeniería de software."
        )
        
    try:
        tech_resp = query_llm(system_instruction, prompt)
    except Exception as e:
        tech_resp = f"Error al generar diagnóstico técnico: {str(e)}"
        
    return {"final_response": tech_resp, "active_agent": "Agente Técnico"}

def pedagogical_node(state: AgentState) -> Dict[str, Any]:
    messages = state.get("messages", [])
    last_message = messages[-1]["content"] if messages else ""
    syllabus = state.get("pedagogical_context", "")
    
    prompt = f"""
    REGLA DE CONTEXTO IMPORTANTE: Formas parte de un sistema inteligente de tutoría multi-agente compuesto por 4 agentes especialistas:
    1. Router (Enrutador): Clasifica las consultas y las redirige al especialista adecuado.
    2. Agente Técnico: Analiza errores de compilación, sintaxis y lógica en el código Java del estudiante.
    3. Agente Pedagógico (Tú): Explica conceptos teóricos apoyándose en el sílabo del curso.
    4. Agente Socrático: Guía al alumno con preguntas de reflexión y pistas sutiles sin darle la solución.
    
    Si el alumno pregunta de cuántos agentes te componen, qué agentes son, o cómo estás estructurado, debes responder detallando explícitamente y de manera amable la existencia de estos 4 agentes especialistas que colaboran en equipo para guiarle.
    
    Sílabo del Curso (Contexto Académico):
    {syllabus}
    
    Pregunta Teórica del Alumno: "{last_message}"
    """
    
    system_instruction = (
        "Eres el Agente Pedagógico de Java y Algoritmia.\n"
        "Explica de forma clara, amena y con analogías la duda conceptual del alumno, relacionándola con las semanas u objetivos del sílabo si es pertinente.\n"
        "REGLA CRÍTICA DE NO FILTRADO DE CÓDIGO DIRECTO: NUNCA entregues el código de solución corregido completo para el reto actual del alumno.\n"
        "Tampoco le muestres la línea de código exacta del alumno corregida directamente. En su lugar, debes explicar el concepto y proporcionar ejemplos de código correctos en un contexto completamente diferente (usando otros nombres de variables, clases y lógica) para ilustrar cómo se aplica el concepto.\n"
        "Nunca des la solución del código directa."
    )
    
    try:
        ped_resp = query_llm(system_instruction, prompt)
    except Exception as e:
        ped_resp = f"Error al generar explicación pedagógica: {str(e)}"
        
    return {"final_response": ped_resp, "active_agent": "Agente Pedagógico"}

def socratic_node(state: AgentState) -> Dict[str, Any]:
    messages = state.get("messages", [])
    last_message = messages[-1]["content"] if messages else ""
    tech_analysis = state.get("technical_analysis", "")
    
    prompt = f"""
    REGLA DE CONTEXTO IMPORTANTE: Formas parte de un sistema inteligente de tutoría multi-agente compuesto por 4 agentes especialistas:
    1. Router (Enrutador): Clasifica las consultas y las redirige al especialista adecuado.
    2. Agente Técnico: Analiza errores de compilación, sintaxis y lógica en el código Java del estudiante.
    3. Agente Pedagógico: Explica conceptos teóricos apoyándose en el sílabo del curso.
    4. Agente Socrático (Tú): Guía al alumno con preguntas de reflexión y pistas sutiles sin darle la solución.
    
    Si el alumno pregunta de cuántos agentes te componen, qué agentes son, o cómo estás estructurado, debes responder detallando explícitamente y de manera amable la existencia de estos 4 agentes especialistas que colaboran en equipo para guiarle.
    
    Diagnóstico Técnico Interno (Lo que está fallando realmente en el código):
    {tech_analysis if tech_analysis else 'No hay errores obvios detectados.'}
    
    Comentario/Pregunta del Alumno: "{last_message}"
    """
    
    system_instruction = (
        "Eres el Agente Socrático de Java. Tu meta es guiar al estudiante usando el método socrático (pistas, preguntas reflexivas).\n"
        "REGLA CRÍTICA: NUNCA entregues código de solución directa ni le digas exactamente qué escribir.\n"
        "REGLA CRÍTICA DE NO FILTRADO DE CÓDIGO DIRECTO: NUNCA entregues el código de solución corregido completo para el reto actual del alumno.\n"
        "Tampoco le muestres la línea de código exacta del alumno corregida directamente. En su lugar, debes explicar el error conceptual y técnicamente, y proporcionar ejemplos de código correctos en un contexto completamente diferente (usando otros nombres de variables, clases y lógica) para ilustrar cómo solucionar el patrón del error. El alumno debe transferir este conocimiento a su propio código.\n"
        "Utiliza el diagnóstico técnico interno para orientar al alumno con pistas sutiles sobre el concepto para que él mismo descubra el error."
    )
    
    try:
        soc_resp = query_llm(system_instruction, prompt)
    except Exception as e:
        soc_resp = f"Error al generar guía socrática: {str(e)}"
        
    return {"final_response": soc_resp, "active_agent": "Agente Socrático"}

def composer_node(state: AgentState) -> Dict[str, Any]:
    return {
        "final_response": state.get("final_response", ""),
        "active_agent": state.get("active_agent", "Tutor Inteligente")
    }

workflow = StateGraph(AgentState)

workflow.add_node("router", router_node)
workflow.add_node("tecnico", technical_node)
workflow.add_node("pedagogico", pedagogical_node)
workflow.add_node("socratico", socratic_node)
workflow.add_node("composer", composer_node)

workflow.set_entry_point("router")

def route_decision(state: AgentState) -> str:
    return state.get("next_agent", "general")

workflow.add_conditional_edges(
    "router",
    route_decision,
    {
        "tecnico": "tecnico",
        "pedagogico": "pedagogico",
        "general": "socratico"
    }
)

workflow.add_edge("tecnico", "composer")
workflow.add_edge("pedagogico", "composer")
workflow.add_edge("socratico", "composer")
workflow.add_edge("composer", END)

compiled_graph = workflow.compile()
