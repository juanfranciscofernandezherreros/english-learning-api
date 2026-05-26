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

# --- PREGUNTAS PREDETERMINADAS PARA EL PRIMER TEST DE NIVELACIÓN ---
PREDETERMINED_QUESTIONS = [
    {
        "id": 1,
        "question": "Hello! What ______ your name?",
        "options": ["is", "am", "are", "be"],
        "correct": "is",
        "points": 1,
        "level_target": "A1"
    },
    {
        "id": 2,
        "question": "Yesterday, I ______ to the cinema with my friends.",
        "options": ["go", "went", "gone", "was go"],
        "correct": "went",
        "points": 1,
        "level_target": "A2"
    },
    {
        "id": 3,
        "question": "I have been living in London ______ three years.",
        "options": ["since", "for", "during", "from"],
        "correct": "for",
        "points": 2,
        "level_target": "B1"
    },
    {
        "id": 4,
        "question": "If I ______ more money, I would buy a new car.",
        "options": ["have", "had", "would have", "had had"],
        "correct": "had",
        "points": 2,
        "level_target": "B2"
    },
    {
        "id": 5,
        "question": "He denied ______ the money from the safe.",
        "options": ["to steal", "stealing", "stole", "have stolen"],
        "correct": "stealing",
        "points": 3,
        "level_target": "C1"
    },
    {
        "id": 6,
        "question": "Little ______ did she know that the surprise party was for her.",
        "options": ["although", "what", "do", "did"],
        "correct": "did",
        "points": 3,
        "level_target": "C2"
    }
]


# --- 1. MODELOS DE DATOS (PYDANTIC SCHEMAS) ---

class UserRegister(BaseModel):
    dni: str = Field(..., max_length=20, example="12345678X")
    nombre: str = Field(..., max_length=100, example="John Doe")

class UserLogin(BaseModel):
    dni: str = Field(..., max_length=20, example="12345678X")

class UserLogout(BaseModel):
    dni: str = Field(..., max_length=20, example="12345678X")

class UserResponse(BaseModel):
    dni: str
    nombre: str
    nivel_calculado: Optional[str] = None
    placement_completed: bool = False
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

class MarkTopicRead(BaseModel):
    dni: str = Field(..., max_length=20, example="12345678X")
    topic_id: int = Field(..., example=1)

# 🔥 NUEVO MODELO: Para recibir la sincronización masiva desde React
class TopicSync(BaseModel):
    dni: str = Field(..., max_length=20, example="12345678K")
    completedTopics: List[int] = Field(..., example=[1, 2, 4])

class ReadTopicInfo(BaseModel):
    topic_id: int
    title: str
    read_at: datetime

class UserProfileResponse(BaseModel):
    dni: str
    nombre: str
    nivel_calculado: Optional[str] = None
    placement_completed: bool = False
    created_at: datetime
    topics_read: List[ReadTopicInfo] = []


# --- 2. FUNCIONES INTERNAS Y BASE DE DATOS ---

def init_db():
    """Inicializa las tablas base de la academia si no existen y aplica parches de migración."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                dni VARCHAR(20) PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                nivel_calculado VARCHAR(50) DEFAULT NULL,
                placement_completed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # PARCHES AUTOMÁTICOS: Asegurar columnas en tablas previas
        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS nivel_calculado VARCHAR(50) DEFAULT NULL;
        """)
        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS placement_completed BOOLEAN DEFAULT FALSE;
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_read_topics (
                user_dni VARCHAR(20) REFERENCES users(dni) ON DELETE CASCADE,
                topic_id INT REFERENCES learning_topics(id) ON DELETE CASCADE,
                read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_dni, topic_id)
            );
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
    if max_possible_points == 0: return "A1 (Principiante)"
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
    version="1.4.0",
    lifespan=lifespan
)


# --- 4. ENDPOINTS EXISTENTES Y ACTUALIZADOS ---

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


@app.post("/auth/logout", tags=["Authentication"])
def logout_user(user_data: UserLogout):
    """Informa al sistema el cierre de sesión del estudiante."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT nombre FROM users WHERE dni = %s;", (user_data.dni.upper(),))
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
            
        return {
            "message": f"Sesión cerrada correctamente para {user['nombre']}.",
            "status": "success"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el servidor: {str(e)}")
    finally:
        cur.close()
        conn.close()


@app.get("/test/placement/generate", response_model=List[PlacementQuestion], tags=["Testing Suite"])
def get_placement_test(
    dni: str, 
    openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key")
):
    """
    Genera o devuelve un examen de nivelación (A1 a C2).
    - Si el usuario ya completó el examen anteriormente, bloquea el acceso.
    - Si es su primera vez, carga preguntas fijas predeterminadas.
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT nivel_calculado, placement_completed FROM users WHERE dni = %s;", (dni.upper(),))
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado. Por favor, regístrese primero.")
        
        if user.get("placement_completed"):
            raise HTTPException(
                status_code=400, 
                detail="Ya has realizado tu prueba de nivelación inicial de forma correcta. No está permitido repetir este test."
            )
        
        if user["nivel_calculado"] is None:
            return PREDETERMINED_QUESTIONS
            
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en base de datos: {str(e)}")
    finally:
        cur.close()
        conn.close()

    if not openai_key:
        raise HTTPException(
            status_code=400, 
            detail="Ya cuentas con un proceso de nivelación iniciado. Envía la cabecera X-OpenAI-Key para continuar."
        )

    client = OpenAI(api_key=openai_key)
    prompt = """
    Eres un examiner oficial de inglés. Diseña un test de nivelación (Placement Test) de exactamente 12 preguntas.
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
    """Evalúa las respuestas de nivelación, calcula el nivel MCER, guarda el examen en el historial y marca el test como completado."""
    earned_points = 0
    max_points = sum(q.points for q in payload.questions)
    questions_dict = {q.id: q for q in payload.questions}
    
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT placement_completed FROM users WHERE dni = %s;", (payload.dni.upper(),))
        user_check = cur.fetchone()
        if user_check and user_check[0]:
            raise HTTPException(status_code=400, detail="Este examen ya fue enviado y procesado previamente.")

        for q_id, user_ans in payload.answers.items():
            if q_id not in questions_dict: 
                continue
                
            q = questions_dict[q_id]
            is_correct = (user_ans == q.correct)
            
            if is_correct:
                earned_points += q.points
            
            cur.execute("""
                INSERT INTO english_test_history (user_dni, question, level, user_answer, correct_answer, is_correct, explanation)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """, (
                payload.dni.upper(), 
                q.question, 
                q.level_target, 
                user_ans, 
                q.correct, 
                is_correct, 
                "Pregunta de Test de Nivelación Inicial"
            ))
            
        calculated_lvl = calculate_mcer_level(earned_points, max_points)
        
        cur.execute("""
            UPDATE users 
            SET nivel_calculado = %s, placement_completed = TRUE 
            WHERE dni = %s;
        """, (calculated_lvl, payload.dni.upper()))
        
        conn.commit()
        
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error en BD al procesar el examen: {str(e)}")
    finally:
        cur.close()
        conn.close()
        
    return {
        "dni": payload.dni,
        "puntos_obtenidos": earned_points,
        "puntos_maximos": max_points,
        "nivel_assigned": calculated_lvl
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


# --- 5. EXÁMENES POR TEMA ---

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
        cur.execute("SELECT * FROM learning_topics WHERE id = %s;", (topic_id,))
        topic = cur.fetchone()
        if not topic:
            raise HTTPException(status_code=404, detail="El tema solicitado no existe en la base de datos.")
    finally:
        cur.close()
        conn.close()

    examples_str = topic['examples']
    if isinstance(examples_str, str):
        examples_str = json.loads(examples_str)

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
        cur.execute("SELECT title FROM learning_topics WHERE id = %s;", (payload.topic_id,))
        topic = cur.fetchone()
        if not topic:
            raise HTTPException(status_code=404, detail="Tema no encontrado.")
            
        topic_title = f"Tema: {topic['title']}"[:50]
        
        questions_dict = {q.id: q for q in payload.questions}
        results = []
        score = 0
        
        for q_id, user_ans in payload.answers.items():
            if q_id not in questions_dict: continue
            q = questions_dict[q_id]
            is_correct = (user_ans == q.correct)
            if is_correct: score += 1
            
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


# --- 6. PROGRESO Y PERFIL DEL USUARIO ---

@app.post("/topics/read", tags=["Library"])
def mark_topic_as_read(payload: MarkTopicRead):
    """Registra que un usuario específico ha leído un tema concreto (Individual)."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM users WHERE dni = %s;", (payload.dni.upper(),))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        
        cur.execute("SELECT 1 FROM learning_topics WHERE id = %s;", (payload.topic_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="El tema solicitado no existe.")

        cur.execute("""
            INSERT INTO user_read_topics (user_dni, topic_id)
            VALUES (%s, %s)
            ON CONFLICT (user_dni, topic_id) DO NOTHING;
        """, (payload.dni.upper(), payload.topic_id))
        
        conn.commit()
        return {"status": "success", "message": "Tema marcado como leído exitosamente."}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error en el servidor: {str(e)}")
    finally:
        cur.close()
        conn.close()


# 🔥 NUEVO ENDPOINT: Sincronización Masiva Directa desde React sin pasar por Proxy
@app.post("/api/auth/sync", tags=["Library"])
def sync_user_progress(payload: TopicSync):
    """
    Sincroniza múltiples temas completados por el alumno de una sola vez.
    Recibe el array 'completedTopics' directo desde el Frontend en React.
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        # 1. Validar existencia del usuario
        cur.execute("SELECT 1 FROM users WHERE dni = %s;", (payload.dni.upper(),))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        
        # 2. Insertar cada ID del lote aplicando control de conflictos
        for topic_id in payload.completedTopics:
            # Validamos que el tema exista para no romper restricciones de clave foránea
            cur.execute("SELECT 1 FROM learning_topics WHERE id = %s;", (topic_id,))
            if not cur.fetchone():
                continue  # Ignora limpiamente IDs inválidos que vengan del cliente
                
            cur.execute("""
                INSERT INTO user_read_topics (user_dni, topic_id)
                VALUES (%s, %s)
                ON CONFLICT (user_dni, topic_id) DO NOTHING;
            """, (payload.dni.upper(), topic_id))
            
        conn.commit()
        return {
            "success": True,
            "message": "Progress synced successfully."
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno durante la sincronización: {str(e)}")
    finally:
        cur.close()
        conn.close()


@app.get("/users/{dni}/profile", response_model=UserProfileResponse, tags=["Profile"])
def get_user_profile(dni: str):
    """Recupera el perfil consolidado del estudiante."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM users WHERE dni = %s;", (dni.upper(),))
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        
        cur.execute("""
            SELECT urt.topic_id, lt.title, urt.read_at
            FROM user_read_topics urt
            JOIN learning_topics lt ON urt.topic_id = lt.id
            WHERE urt.user_dni = %s
            ORDER BY urt.read_at DESC;
        """, (dni.upper(),))
        read_topics = cur.fetchall()
        
        return {
            "dni": user["dni"],
            "nombre": user["nombre"],
            "nivel_calculado": user["nivel_calculado"],
            "placement_completed": user.get("placement_completed", False),
            "created_at": user["created_at"],
            "topics_read": read_topics
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar el perfil: {str(e)}")
    finally:
        cur.close()
        conn.close()
