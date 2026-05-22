import json
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.extras import RealDictCursor
from openai import OpenAI

# --- CONFIGURACIÓN DE CONEXIONES ---
DB_CONFIG = {
    "host": "ep-old-field-ambx94k5-pooler.c-5.us-east-1.aws.neon.tech",
    "port": 5432,
    "database": "neondb",
    "user": "neondb_owner",
    "password": "npg_urVnAFP3Hy4M"
}

# --- 1. MODELOS DE DATOS (PYDANTIC SCHEMAS) ---
class UserRegister(BaseModel):
    dni: str = Field(..., max_length=20, example="12345678X")
    nombre: str = Field(..., max_length=100, example="John Doe")

class UserLogin(BaseModel):
    dni: str = Field(..., max_length=20, example="12345678X")

class UserResponse(BaseModel):
    dni: str
    nombre: str
    nivel_calculado: Optional[str] = None
    created_at: datetime

class TopicResponse(BaseModel):
    id: int
    title: str
    summary: str
    content: str
    examples: List[str]

class PlacementQuestion(BaseModel):
    id: int
    question: str
    options: List[str]
    correct: str
    points: int
    level_target: str

class AdaptiveQuestion(BaseModel):
    id: int
    question: str
    options: List[str]
    correct: str
    explanation: str

class PlacementSubmit(BaseModel):
    dni: str
    questions: List[PlacementQuestion]
    answers: Dict[int, str]

class AdaptiveSubmit(BaseModel):
    dni: str
    level: str
    questions: List[AdaptiveQuestion]
    answers: Dict[int, str]

# --- NUEVOS MODELOS PARA PASAR TEST POR TEMAS ---
class TopicQuestion(BaseModel):
    id: int
    question: str
    options: List[str]
    correct: str
    explanation: str

class TopicSubmit(BaseModel):
    dni: str
    topic_id: int
    questions: List[TopicQuestion]
    answers: Dict[int, str]


# --- 2. FUNCIONES INTERNAS Y BASE DE DATOS ---
def init_db():
    """Inicializa las tablas base de la academia si no existen"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                dni VARCHAR(20) PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                nivel_calculado VARCHAR(50) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS english_test_history (
                id SERIAL PRIMARY KEY,
                user_dni VARCHAR(20) REFERENCES users(dni) ON DELETE CASCADE,
                question TEXT NOT NULL,
                level VARCHAR(50) NOT NULL,
                user_answer TEXT NOT NULL,
                correct_answer TEXT NOT NULL,
                is_correct BOOLEAN NOT NULL,
                explanation TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS learning_topics (
                id SERIAL PRIMARY KEY,
                title VARCHAR(100) UNIQUE NOT NULL,
                summary TEXT NOT NULL,
                content TEXT NOT NULL,
                examples JSONB NOT NULL
            );
        """)
        conn.commit()

        # Semilla opcional si está vacía
        cur.execute("SELECT COUNT(*) FROM learning_topics;")
        if cur.fetchone()[0] == 0:
            cur.execute("""
                INSERT INTO learning_topics (title, summary, content, examples) VALUES 
                ('Present Simple', 'Rutinas y hechos.', 'Forma con infinitivo...', '["I work every day.", "She speaks fluently."]'),
                ('Present Continuous', 'Acciones del momento.', 'Auxiliar to be + -ing...', '["We are developing an API."]'),
                ('Past Simple', 'Acciones terminadas.', 'Terminación -ed o irregulares...', '["They watched a movie."]'),
                ('Past Continuous', 'Acciones en desarrollo en el pasado.', 'Was/were + -ing...', '["I was walking when it rained."]'),
                ('Present Perfect', 'Conecta pasado y presente.', 'Auxiliar have/has + participio...', '["She has visited Paris."]');
            """)
            conn.commit()
    finally:
        cur.close()
        conn.close()

def get_recent_failures(dni: str, lvl: str, limit: int = 5) -> List[dict]:
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT question, correct_answer, explanation 
            FROM english_test_history 
            WHERE user_dni = %s AND level = %s AND is_correct = FALSE 
            ORDER BY created_at DESC LIMIT %s;
        """, (dni, lvl, limit))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

def calculate_mcer_level(score: int, max_possible_points: int) -> str:
    percentage = (score / max_possible_points) * 100
    if percentage < 20: return "A1 (Principiante)"
    elif percentage < 40: return "A2 (Elemental)"
    elif percentage < 60: return "B1 (Intermedio)"
    elif percentage < 75: return "B2 (Intermedio Alto)"
    elif percentage < 90: return "C1 (Avanzado)"
    else: return "C2 (Maestría)"


# --- 3. CICLO DE VIDA DE FASTAPI (LIFESPAN) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="AI English Academy API",
    description="Backend adaptativo para evaluación y librería de inglés mediante IA",
    version="1.1.0",
    lifespan=lifespan
)


# --- 4. ENDPOINTS EXISTENTES ---

@app.get("/topics", response_model=List[TopicResponse], tags=["Library"])
def get_topics():
    """Obtiene todo el temario disponible en la base de datos."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM learning_topics ORDER BY id ASC;")
        topics = cur.fetchall()
        for t in topics:
            if isinstance(t['examples'], str):
                t['examples'] = json.loads(t['examples'])
        return topics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@app.post("/auth/register", response_model=UserResponse, status_code=201, tags=["Authentication"])
def register_user(user_data: UserRegister):
    """Registra un nuevo usuario en el sistema usando su DNI."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM users WHERE dni = %s;", (user_data.dni.upper(),))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="El usuario con este DNI ya existe.")
        
        cur.execute(
            "INSERT INTO users (dni, nombre) VALUES (%s, %s) RETURNING *;",
            (user_data.dni.upper(), user_data.nombre)
        )
        new_user = cur.fetchone()
        conn.commit()
        return new_user
    finally:
        cur.close()
        conn.close()


@app.post("/auth/login", response_model=UserResponse, tags=["Authentication"])
def login_user(user_data: UserLogin):
    """Inicia sesión y recupera la información del perfil del estudiante."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM users WHERE dni = %s;", (user_data.dni.upper(),))
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        return user
    finally:
        cur.close()
        conn.close()


@app.get("/test/placement/generate", response_model=List[PlacementQuestion], tags=["Testing Suite"])
def get_placement_test(openai_key: str = Header(..., alias="X-OpenAI-Key")):
    """Genera dinámicamente un examen de nivelación (A1 a C2) mediante GPT-4o."""
    client = OpenAI(api_key=openai_key)
    prompt = """
    Eres un examinador oficial de inglés. Diseña un test de nivelación (Placement Test) de exactamente 12 preguntas.
    El test debe ser progresivo (A1 a C2). Devuelve obligatoriamente un JSON con clave "questions".
    Cada pregunta debe estructurarse así:
    {
        "id": entero del 1 al 12,
        "question": "Frase o enunciado en inglés",
        "options": ["Opción A", "Opción B", "Opción C", "Opción D"],
        "correct": "La opción exacta que responde correctamente",
        "points": un entero del 1 al 3 que represente el peso,
        "level_target": "A1, A2, B1, B2, C1 o C2"
    }
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.4
        )
        return json.loads(response.choices[0].message.content).get("questions", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error con OpenAI: {str(e)}")


@app.post("/test/placement/submit", tags=["Testing Suite"])
def submit_placement_test(payload: PlacementSubmit):
    """Evalúa las respuestas de nivelación, calcula el nivel MCER y lo guarda en el perfil."""
    earned_points = 0
    max_points = sum(q.points for q in payload.questions)
    questions_dict = {q.id: q for q in payload.questions}
    
    for q_id, user_ans in payload.answers.items():
        if q_id in questions_dict and user_ans == questions_dict[q_id].correct:
            earned_points += questions_dict[q_id].points
            
    calculated_lvl = calculate_mcer_level(earned_points, max_points)
    
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET nivel_calculado = %s WHERE dni = %s;", (calculated_lvl, payload.dni.upper()))
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en BD: {str(e)}")
    finally:
        cur.close()
        conn.close()
        
    return {
        "dni": payload.dni,
        "puntos_obtenidos": earned_points,
        "puntos_maximos": max_points,
        "nivel_asignado": calculated_lvl
    }


@app.get("/test/adaptive/generate", response_model=List[AdaptiveQuestion], tags=["Testing Suite"])
def get_adaptive_test(
    dni: str, 
    level: str, 
    num_questions: int = 5, 
    openai_key: str = Header(..., alias="X-OpenAI-Key")
):
    """Genera preguntas personalizadas basadas en los errores previos del alumno."""
    past_failures = get_recent_failures(dni.upper(), level)
    failures_context = ""
    
    if past_failures:
        failures_context = "\n⚠️ ENFOQUE ADAPTATIVO REQUERIDO:\nEl usuario ha fallado recientemente en estas preguntas. Analiza los errores y genera preguntas NUEVAS sobre los mismos conceptos gramaticales en contextos diferentes:\n"
        for f in past_failures:
            failures_context += f"- Fallada: '{f['question']}' (Correcta era: '{f['correct_answer']}'). Regla: {f['explanation']}\n"

    client = OpenAI(api_key=openai_key)
    prompt = f"""
    Eres un profesor de inglés experto. Genera exactamente {num_questions} preguntas de opción múltiple adaptadas al nivel {level}.
    {failures_context}
    
    Devuelve obligatoriamente un objeto JSON con la clave "questions". Estructura:
    {{
        "id": entero secuencial,
        "question": "Frase con '......' o pregunta directa",
        "options": ["A", "B", "C", "D"],
        "correct": "La opción exacta correcta",
        "explanation": "Breve explicación en español de la regla"
    }}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        return json.loads(response.choices[0].message.content).get("questions", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error con OpenAI: {str(e)}")


@app.post("/test/adaptive/submit", tags=["Testing Suite"])
def submit_adaptive_test(payload: AdaptiveSubmit):
    """Procesa el examen adaptativo, registra el historial en la base de datos."""
    questions_dict = {q.id: q for q in payload.questions}
    results = []
    score = 0
    
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        for q_id, user_ans in payload.answers.items():
            if q_id not in questions_dict: continue
            q = questions_dict[q_id]
            is_correct = (user_ans == q.correct)
            if is_correct: score += 1
                
            cur.execute("""
                INSERT INTO english_test_history (user_dni, question, level, user_answer, correct_answer, is_correct, explanation)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """, (payload.dni.upper(), q.question, payload.level, user_ans, q.correct, is_correct, q.explanation))
            
            results.append({
                "question_id": q_id,
                "is_correct": is_correct,
                "explanation": q.explanation
            })
        conn.commit()
        return {"puntuacion": f"{score} / {len(payload.questions)}", "detalles": results}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# --- 5. NUEVA FUNCIONALIDAD: GENERACIÓN DE EXÁMENES POR TEMA ---

@app.get("/test/topic/generate", response_model=List[TopicQuestion], tags=["Topic Testing"])
def generate_test_by_topic(
    topic_id: int,
    num_questions: int = 5,
    openai_key: str = Header(..., alias="X-OpenAI-Key")
):
    """Busca un tema específico en la base de datos y obliga a la IA a estructurar un test exclusivo sobre él."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # 1. Extraer los datos del tema del curso
        cur.execute("SELECT * FROM learning_topics WHERE id = %s;", (topic_id,))
        topic = cur.fetchone()
        if not topic:
            raise HTTPException(status_code=404, detail="El tema solicitado no existe en la base de datos.")
    finally:
        cur.close()
        conn.close()

    # Formatear ejemplos
    examples_str = topic['examples']
    if isinstance(examples_str, str):
        examples_str = json.loads(examples_str)

    # 2. Entrenar el Prompt con el contexto real extraído de la base de datos
    client = OpenAI(api_key=openai_key)
    prompt = f"""
    Eres un profesor de inglés experto encargado de crear exámenes temáticos. 
    Tu objetivo es generar exactamente {num_questions} preguntas de opción múltiple enfocadas ÚNICAMENTE en evaluar el siguiente tema gramatical:

    TEMA: {topic['title']}
    RESUMEN CONCEPTUAL: {topic['summary']}
    EXPLICACIÓN TEÓRICA: {topic['content']}
    EJEMPLOS DE REFERENCIA: {examples_str}

    REGLAS ESTRICTAS:
    1. Todas las preguntas deben evaluar directamente la estructura explicada arriba.
    2. No utilices conceptos avanzados que no correspondan a este tema.
    3. Devuelve obligatoriamente un objeto JSON con la clave "questions".

    Estructura del JSON:
    {{
        "questions": [
            {{
                "id": entero secuencial comenzando en 1,
                "question": "Oración en inglés con '......' para rellenar o pregunta directa relevante",
                "options": ["Opción A", "Opción B", "Opción C", "Opción D"],
                "correct": "La opción exacta que responde correctamente",
                "explanation": "Breve explicación didáctica en español de por qué es la respuesta correcta basándote en la teoría dada."
            }}
        ]
    }}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.5
        )
        return json.loads(response.choices[0].message.content).get("questions", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en OpenAI al procesar el tema: {str(e)}")


@app.post("/test/topic/submit", tags=["Topic Testing"])
def submit_topic_test(payload: TopicSubmit):
    """Procesa los resultados de un examen por temas y los guarda de manera segura en el historial general."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Obtener el título del tema para el registro de nivel
        cur.execute("SELECT title FROM learning_topics WHERE id = %s;", (payload.topic_id,))
        topic = cur.fetchone()
        if not topic:
            raise HTTPException(status_code=404, detail="Tema no encontrado.")
            
        topic_title = f"Tema: {topic['title']}"[:50] # Asegurar límite de la columna
        
        questions_dict = {q.id: q for q in payload.questions}
        results = []
        score = 0
        
        for q_id, user_ans in payload.answers.items():
            if q_id not in questions_dict: continue
            q = questions_dict[q_id]
            is_correct = (user_ans == q.correct)
            if is_correct: score += 1
            
            # Insertar en la tabla de historial tradicional
            cur.execute("""
                INSERT INTO english_test_history (user_dni, question, level, user_answer, correct_answer, is_correct, explanation)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """, (payload.dni.upper(), q.question, topic_title, user_ans, q.correct, is_correct, q.explanation))
            
            results.append({
                "question_id": q_id,
                "is_correct": is_correct,
                "explanation": q.explanation
            })
            
        conn.commit()
        return {
            "tema_evaluado": topic['title'],
            "puntuacion": f"{score} / {len(payload.questions)}",
            "detalles": results
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
