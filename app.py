import streamlit as st
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from openai import OpenAI
from datetime import datetime

# Configuración de la página
st.set_page_config(page_title="AI Adaptive English Test", page_icon="🇬🇧", layout="centered")

# --- 1. CONFIGURACIÓN DE CONEXIONES ---
DB_CONFIG = {
    "host": "ep-old-field-ambx94k5-pooler.c-5.us-east-1.aws.neon.tech",
    "port": 5432,
    "database": "neondb",
    "user": "neondb_owner",
    "password": "npg_urVnAFP3Hy4M"
}

# --- 2. FUNCIONES DE BASE DE DATOS ---
def init_db():
    """Crea las tablas de usuarios e historial si no existen"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # Tabla de Usuarios
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                dni VARCHAR(20) PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Tabla de Historial (Modificada para incluir el DNI como Foreign Key)
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
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"Error al inicializar la base de datos: {e}")

def get_or_create_user(dni, nombre=None):
    """Verifica si el usuario existe. Si no existe y se pasa un nombre, lo registra."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Buscar usuario
        cur.execute("SELECT * FROM users WHERE dni = %s;", (dni,))
        user = cur.fetchone()
        
        if not user and nombre:
            # Registrar nuevo usuario
            cur.execute("INSERT INTO users (dni, nombre) VALUES (%s, %s) RETURNING *;", (dni, nombre))
            user = cur.fetchone()
            conn.commit()
            
        cur.close()
        conn.close()
        return user
    except Exception as e:
        st.error(f"Error al gestionar el usuario en la BD: {e}")
        return None

def save_answer_to_db(dni, question, lvl, user_ans, correct_ans, is_correct, explanation):
    """Guarda cada respuesta vinculándola al DNI del usuario"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO english_test_history (user_dni, question, level, user_answer, correct_answer, is_correct, explanation)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """, (dni, question, lvl, user_ans, correct_ans, is_correct, explanation))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"Error al guardar en la base de datos: {e}")

def get_recent_failures(dni, lvl, limit=5):
    """Recupera los últimos fallos EXCLUSIVOS del usuario activo en el nivel seleccionado"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT question, correct_answer, explanation 
            FROM english_test_history 
            WHERE user_dni = %s AND level = %s AND is_correct = FALSE 
            ORDER BY created_at DESC 
            LIMIT %s;
        """, (dni, lvl, limit))
        failures = cur.fetchall()
        cur.close()
        conn.close()
        return failures
    except Exception as e:
        st.error(f"Error al consultar fallos previos: {e}")
        return []

# Inicializar estructuras de datos al cargar la app
init_db()

# --- 3. ESTADOS DE SESIÓN DE STREAMLIT ---
if "user" not in st.session_state:
    st.session_state.user = None  # Almacenará los datos del usuario logueado
if "questions" not in st.session_state:
    st.session_state.questions = None

# --- 4. INTERFAZ DE LOGUEO Y REGISTRO ---
if st.session_state.user is None:
    st.title("🔐 Acceso al Sistema de Tests")
    
    tab_login, tab_register = st.tabs(["Iniciar Sesión", "Registrarse"])
    
    with tab_login:
        with st.form("login_form"):
            login_dni = st.text_input("Introduce tu DNI/NIE", key="login_dni_input").strip().upper()
            login_submit = st.form_submit_button("Ingresar")
            
            if login_submit:
                if not login_dni:
                    st.warning("Por favor, introduce tu DNI.")
                else:
                    user = get_or_create_user(login_dni)
                    if user:
                        st.session_state.user = user
                        st.success(f"¡Bienvenido de nuevo, {user['nombre']}!")
                        st.rerun()
                    else:
                        st.error("El DNI introducido no está registrado.")
                        
    with tab_register:
        with st.form("register_form"):
            reg_dni = st.text_input("DNI/NIE del nuevo usuario").strip().upper()
            reg_nombre = st.text_input("Nombre Completo")
            reg_submit = st.form_submit_button("Crear Cuenta")
            
            if reg_submit:
                if not reg_dni or not reg_nombre:
                    st.warning("Todos los campos son obligatorios.")
                else:
                    # Comprobar si ya existe
                    existing_user = get_or_create_user(reg_dni)
                    if existing_user:
                        st.error("Este DNI ya se encuentra registrado.")
                    else:
                        user = get_or_create_user(reg_dni, reg_nombre)
                        if user:
                            st.session_state.user = user
                            st.success(f"Cuenta creada con éxito. ¡Bienvenido {reg_nombre}!")
                            st.rerun()

# --- 5. APLICACIÓN PRINCIPAL (USUARIO AUTENTICADO) ---
else:
    user_active = st.session_state.user
    
    # Barra lateral de configuración y desconexión
    st.sidebar.title(f"👤 {user_active['nombre']}")
    st.sidebar.caption(f"DNI: {user_active['dni']}")
    
    if st.sidebar.button("🚪 Cerrar Sesión"):
        st.session_state.user = None
        st.session_state.questions = None
        st.rerun()
        
    st.sidebar.write("---")
    st.sidebar.header("Configuración de la IA")
    api_key = st.sidebar.text_input("Introduce tu OpenAI API Key", type="password")

    level = st.sidebar.selectbox(
        "Nivel del test (MCER)", 
        ["A1 (Principiante)", "A2 (Elemental)", "B1 (Intermedio)", "B2 (Intermedio Alto)", "C1 (Avanzado)", "C2 (Maestría)"]
    )
    num_questions = st.sidebar.slider("Número de preguntas", min_value=3, max_value=10, value=5)

    # Control de cambio de nivel
    if "current_level" not in st.session_state:
        st.session_state.current_level = level

    if st.session_state.current_level != level:
        st.session_state.questions = None
        st.session_state.current_level = level

    st.title("🇬🇧 Test de Inglés Adaptativo")
    st.write(f"Hola **{user_active['nombre']}**. Tus resultados se guardarán vinculados a tu DNI.")

    # --- 6. FUNCIÓN DE GENERACIÓN ADAPTATIVA ---
    def generate_questions_from_api(api_key, dni, lvl, num):
        client = OpenAI(api_key=api_key)
        
        # Filtrar fallos exclusivamente de este usuario
        past_failures = get_recent_failures(dni, lvl)
        failures_context = ""
        
        if past_failures:
            failures_context = "\n⚠️ ENFOQUE ADAPTATIVO REQUERIDO:\nEl usuario ha fallado recientemente en las siguientes preguntas de este nivel. Analiza sus errores gramaticales o léxicos y genera preguntas NUEVAS que evalúen esos MISMOS conceptos problemáticos pero usando contextos o frases totalmente diferentes para ayudarle a reforzarlos:\n"
            for f in past_failures:
                failures_context += f"- Pregunta fallada: '{f['question']}' (La respuesta correcta era: '{f['correct_answer']}'). Contexto/Regla: {f['explanation']}\n"

        prompt = f"""
        Eres un profesor de inglés experto encargado de crear un examen de opción múltiple adaptativo.
        Genera exactamente {num} preguntas en inglés adaptadas al nivel {lvl}.
        {failures_context}
        
        Debes devolver OBLIGATORIAMENTE un objeto JSON que contenga una lista bajo la clave "questions".
        Cada pregunta dentro de la lista debe seguir esta estructura exacta:
        {{
            "id": un número entero secuencial empezando en 1,
            "question": "La frase en inglés con la laguna representada por '......' o una pregunta directa",
            "options": ["Opción A", "Opción B", "Opción C", "Opción D"],
            "correct": "La opción exacta que responde correctamente a la pregunta",
            "explanation": "Una breve explicación en español de por qué es la correcta y qué regla gramatical o léxica se aplica"
        }}
        Asegúrate de que solo una de las opciones sea gramaticalmente correcta y que las preguntas sean variadas.
        """
        
        try:
            response = client.chat.completions.create(
                model="gpt-4o", 
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7
            )
            result = json.loads(response.choices[0].message.content)
            return result.get("questions", [])
        except Exception as e:
            st.error(f"Error al conectar con OpenAI: {e}")
            return None

    # --- 7. LÓGICA DE LA INTERFAZ DEL TEST ---
    if not api_key:
        st.warning("🔑 Por favor, introduce tu OpenAI API Key en la barra lateral para comenzar.")
    else:
        if st.sidebar.button("🔄 Generar Nuevo Test") or st.session_state.questions is None:
            with st.spinner("La IA está analizando tu historial y diseñando tus preguntas..."):
                st.session_state.questions = generate_questions_from_api(api_key, user_active['dni'], level, num_questions)
                st.rerun()

    if st.session_state.questions:
        # Mostrar feedback de refuerzo basado en el DNI actual
        failures_count = len(get_recent_failures(user_active['dni'], level))
        if failures_count > 0:
            st.caption(f"🔄 Se han detectado fallos previos en el nivel {level} para tu usuario. Este test incluye preguntas de refuerzo personalizadas.")
        
        with st.form("quiz_form"):
            user_answers = {}
            
            for q in st.session_state.questions:
                st.markdown(f"### Pregunta {q['id']}")
                user_answers[q["id"]] = st.radio(
                    q["question"],
                    options=q["options"],
                    index=None,
                    key=f"q_{level}_{q['id']}"
                )
                st.write("---")
                
            submitted = st.form_submit_button("Enviar Respuestas")

        if submitted:
            if None in user_answers.values():
                st.warning("⚠️ Por favor, responde a todas las preguntas antes de enviar.")
            else:
                score = 0
                st.header("📊 Resultados del Test")
                
                with st.spinner("Guardando resultados en tu cuenta..."):
                    for q in st.session_state.questions:
                        ans = user_answers[q["id"]]
                        is_correct = (ans == q["correct"])
                        
                        # GUARDAR EN POSTGRES VINCULANDO AL USUARIO
                        save_answer_to_db(
                            dni=user_active['dni'],
                            question=q["question"],
                            lvl=level,
                            user_ans=ans,
                            correct_ans=q["correct"],
                            is_correct=is_correct,
                            explanation=q["explanation"]
                        )
                        
                        if is_correct:
                            score += 1
                            st.success(f"**Pregunta {q['id']}: ¡Correcta!**  \n*{q['question']}*  \n👉 Seleccionaste: `{ans}`")
                        else:
                            st.error(f"**Pregunta {q['id']}: Incorrecta (Guardada para repaso)**  \n*{q['question']}*  \n❌ Tu respuesta: `{ans}`  \n✅ Correcta: `{q['correct']}`")
                        
                        st.info(f"💡 **Explicación:** {q['explanation']}")
                        st.write("")
                
                total = len(st.session_state.questions)
                st.subheader(f"Tu puntuación final: {score} / {total}")
                
                if score == total:
                    st.balloons()
                    st.success("🏆 ¡Excelente! Rendimiento perfecto.")
                else:
                    st.warning("📝 Los fallos se han registrado en tu perfil para el próximo test.")
