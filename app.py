import streamlit as st
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from openai import OpenAI
from datetime import datetime

# Configuración de la página
st.set_page_config(page_title="AI Adaptive English Test & Library", page_icon="🇬🇧", layout="centered")

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
    """Crea las tablas de usuarios, historial y temario si no existen"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # Tabla de Usuarios (Incluye la columna nivel_calculado)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                dni VARCHAR(20) PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                nivel_calculado VARCHAR(50) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Tabla de Historial
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

        # Tabla de Temario Estilo Libro
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

        # Insertar contenido semilla de cortesía si la tabla está vacía
        cur.execute("SELECT COUNT(*) FROM learning_topics;")
        if cur.fetchone()[0] == 0:
            cur.execute("""
                INSERT INTO learning_topics (title, summary, content, examples) VALUES 
                (
                    'Present Simple', 
                    'Utilizado para rutinas, hechos generales y situaciones permanentes.',
                    'El Present Simple se forma con el infinitivo del verbo. Recuerda que en la tercera persona del singular (he, she, it) se añade una "-s" o "-es" al final del verbo principal en oraciones afirmativas. Para negar o preguntar, recurrimos al auxiliar *do* o *does*.',
                    '["I work from home every day.", "She speaks English fluently.", "They do not like coffee."]'
                ),
                (
                    'Present Continuous', 
                    'Utilizado para acciones que están ocurriendo en este preciso instante.',
                    'El Present Continuous se construye utilizando el verbo auxiliar *to be* en presente (am, is, are) seguido del verbo principal con la terminación "-ing" (gerundio). Sirve también para planes futuros ya confirmados.',
                    '["John is sleeping right now.", "We are developing a web application.", "Are you listening to music?"]'
                ),
                (
                    'Past Simple', 
                    'Utilizado para acciones puntuales que comenzaron y terminaron en el pasado.',
                    'Para los verbos regulares, el pasado se forma añadiendo la terminación "-ed". Los verbos irregulares cambian su forma por completo. El verbo auxiliar para negar e interrogar en este tiempo es *did*.',
                    '["They watched a movie last night.", "He went to London in 2024.", "Did you finish the report?"]'
                ),
                (
                    'Past Continuous', 
                    'Utilizado para describir acciones que se estaban desarrollando en un momento específico del pasado.',
                    'Se estructura utilizando el pasado del verbo auxiliar *to be* (was/were) más el gerundio del verbo principal (-ing). Se usa frecuentemente para preparar el escenario de una historia o interrumpir una acción larga con una corta en Past Simple.',
                    '["I was walking down the street when it started to rain.", "They were studying all night long.", "What were you doing at 8 PM yesterday?"]'
                ),
                (
                    'Present Perfect', 
                    'Conecta el pasado con el presente; enfocado en el resultado o en experiencias.',
                    'Se forma usando el auxiliar *have/has* junto al participio pasado del verbo principal (verbos regulares con "-ed" o la tercera columna de los irregulares). Importante: no se menciona un tiempo específico terminado.',
                    '["I have lost my keys.", "She has visited Paris three times.", "Have you ever eaten sushi?"]'
                );
            """)
            conn.commit()

        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"Error al inicializar la base de datos: {e}")

def get_learning_topics():
    """Recupera la lista de lecciones disponibles para el temario público"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM learning_topics ORDER BY id ASC;")
        topics = cur.fetchall()
        cur.close()
        conn.close()
        return topics
    except Exception as e:
        st.error(f"Error al cargar el temario de la BD: {e}")
        return []

def get_or_create_user(dni, nombre=None):
    """Verifica si el usuario existe. Si no existe y se pasa un nombre, lo registra."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT * FROM users WHERE dni = %s;", (dni,))
        user = cur.fetchone()
        
        if not user and nombre:
            cur.execute("INSERT INTO users (dni, nombre) VALUES (%s, %s) RETURNING *;", (dni, nombre))
            user = cur.fetchone()
            conn.commit()
            
        cur.close()
        conn.close()
        return user
    except Exception as e:
        st.error(f"Error al gestionar el usuario en la BD: {e}")
        return None

def update_user_level(dni, lvl):
    """Guarda el nivel calculado tras el test inicial"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("UPDATE users SET nivel_calculado = %s WHERE dni = %s;", (lvl, dni))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"Error al actualizar el nivel en la BD: {e}")

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
    """Recupera los últimos fallos del usuario en el nivel seleccionado"""
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
    st.session_state.user = None  
if "questions" not in st.session_state:
    st.session_state.questions = None
if "capitulo_seleccionado" not in st.session_state:
    st.session_state.capitulo_seleccionado = 0  # Índice por defecto para el temario

# --- 4. ENTORNO PÚBLICO (CONTENIDO ANTES DE INICIAR SESIÓN) ---
if st.session_state.user is None:
    
    st.title("📖 English Academy & Testing Suite")
    st.write("Bienvenido. Puedes revisar nuestro libro de gramática interactiva de libre acceso o ingresar a tu cuenta privada en el panel lateral para evaluar tu progreso adaptativo.")
    
    # Barra lateral pública: Control de accesos
    st.sidebar.title("🔐 Control de Acceso")
    opcion_acceso = st.sidebar.radio("Elige una opción:", ["Iniciar Sesión", "Registrarse"])
    
    if opcion_acceso == "Iniciar Sesión":
        with st.sidebar.form("login_form"):
            login_dni = st.text_input("Introduce tu DNI/NIE").strip().upper()
            login_submit = st.form_submit_button("Ingresar")
            if login_submit:
                if not login_dni:
                    st.sidebar.warning("Introduce tu DNI.")
                else:
                    user = get_or_create_user(login_dni)
                    if user:
                        st.session_state.user = user
                        st.success(f"¡Bienvenido de nuevo, {user['nombre']}!")
                        st.rerun()
                    else:
                        st.sidebar.error("DNI no registrado.")
                        
    elif opcion_acceso == "Registrarse":
        with st.sidebar.form("register_form"):
            reg_dni = st.text_input("DNI/NIE").strip().upper()
            reg_nombre = st.text_input("Nombre Completo")
            reg_submit = st.form_submit_button("Crear Cuenta")
            if reg_submit:
                if not reg_dni or not reg_nombre:
                    st.sidebar.warning("Todos los campos son obligatorios.")
                else:
                    existing_user = get_or_create_user(reg_dni)
                    if existing_user:
                        st.sidebar.error("Este DNI ya existe.")
                    else:
                        user = get_or_create_user(reg_dni, reg_nombre)
                        if user:
                            st.session_state.user = user
                            st.success(f"¡Cuenta creada con éxito!")
                            st.rerun()
                            
    # Área central pública: Carga del libro de texto desde SQL
    st.write("---")
    st.subheader("📘 Temario Oficial del Curso")
    
    lecciones = get_learning_topics()
    
    if lecciones:
        nombres_lecciones = [l['title'] for l in lecciones]
        
        # Callback para registrar el cambio de lección de forma segura en la sesión
        def cambiar_leccion():
            for idx, l in enumerate(lecciones):
                if l['title'] == st.session_state.selector_libro:
                    st.session_state.capitulo_seleccionado = idx
                    break

        leccion_seleccionada = st.selectbox(
            "📖 Selecciona un capítulo para estudiar:", 
            nombres_lecciones,
            index=st.session_state.capitulo_seleccionado,
            key="selector_libro",
            on_change=cambiar_leccion
        )
        
        # Recuperar los datos del capítulo empleando el índice guardado en sesión
        datos_leccion = lecciones[st.session_state.capitulo_seleccionado]
        
        # Renderizado estético de la lección
        st.markdown(f"## {datos_leccion['title']}")
        st.info(f"💡 **En resumen:** {datos_leccion['summary']}")
        st.write(datos_leccion['content'])
        
        st.markdown("### 📝 Ejemplos prácticos de uso:")
        ejemplos = datos_leccion['examples']
        if isinstance(ejemplos, str):
            ejemplos = json.loads(ejemplos)
            
        for ej in ejemplos:
            st.markdown(f"- *{ej}*")
    else:
        st.write("No hay lecciones cargadas actualmente en la base de datos.")

# --- 5. ENTORNO PRIVADO (USUARIO AUTENTICADO) ---
else:
    user_active = st.session_state.user
    
    st.sidebar.title(f"👤 {user_active['nombre']}")
    st.sidebar.caption(f"DNI: {user_active['dni']}")
    
    if st.sidebar.button("🚪 Cerrar Sesión"):
        st.session_state.user = None
        st.session_state.questions = None
        if "placement_questions" in st.session_state:
            del st.session_state.placement_questions
        st.rerun()
        
    st.sidebar.write("---")

    def calculate_mcer_level(score, max_possible_points):
        percentage = (score / max_possible_points) * 100
        if percentage < 20: return "A1 (Principiante)"
        elif percentage < 40: return "A2 (Elemental)"
        elif percentage < 60: return "B1 (Intermedio)"
        elif percentage < 75: return "B2 (Intermedio Alto)"
        elif percentage < 90: return "C1 (Avanzado)"
        else: return "C2 (Maestría)"

    # --- CASO A: TEST INICIAL DE NIVELACIÓN ---
    if user_active.get('nivel_calculado') is None:
        st.title("🎯 Test de Nivelación Inicial")
        st.write("La IA necesita evaluar tu nivel base. Este examen consta de 12 preguntas de dificultad progresiva (de A1 a C2).")
        
        api_key_init = st.text_input("Introduce tu OpenAI API Key para iniciar la prueba", type="password")
        
        def generate_placement_test(api_key):
            client = OpenAI(api_key=api_key)
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
                st.error(f"Error al conectar con OpenAI: {e}")
                return None

        if not api_key_init:
            st.warning("🔑 Por favor, proporciona tu API Key para poder generar el examen de nivelación.")
        else:
            if "placement_questions" not in st.session_state:
                st.session_state.placement_questions = None

            if st.button("🚀 Generar Test de Ubicación") or st.session_state.placement_questions is None:
                with st.spinner("Preparando tus preguntas multinivel..."):
                    st.session_state.placement_questions = generate_placement_test(api_key_init)
                    st.rerun()

            if st.session_state.placement_questions:
                with st.form("placement_form"):
                    p_answers = {}
                    for q in st.session_state.placement_questions:
                        st.markdown(f"### Pregunta {q['id']} <_Nivel estimado: {q['level_target']}_>", unsafe_allow_html=True)
                        p_answers[q["id"]] = st.radio(q["question"], options=q["options"], index=None, key=f"placement_{q['id']}")
                        st.write("---")
                        
                    submit_placement = st.form_submit_button("Finalizar Evaluación")
                    
                if submit_placement:
                    if None in p_answers.values():
                        st.warning("⚠️ Debes contestar a todas las preguntas.")
                    else:
                        earned_points = 0
                        max_points = sum(q["points"] for q in st.session_state.placement_questions)
                        for q in st.session_state.placement_questions:
                            if p_answers[q["id"]] == q["correct"]:
                                earned_points += q["points"]
                                
                        calculated_lvl = calculate_mcer_level(earned_points, max_points)
                        update_user_level(user_active['dni'], calculated_lvl)
                        st.session_state.user['nivel_calculado'] = calculated_lvl
                        
                        st.success(f"🎉 ¡Test Finalizado! Tu nivel asignado es: **{calculated_lvl}**")
                        st.balloons()
                        del st.session_state.placement_questions
                        st.button("Acceder al Panel Principal", on_click=lambda: st.rerun())

    # --- CASO B: SISTEMA ADAPTATIVO DIARIO ---
    else:
        st.sidebar.header("Configuración de la IA")
        api_key = st.sidebar.text_input("Introduce tu OpenAI API Key", type="password")

        lista_niveles = ["A1 (Principiante)", "A2 (Elemental)", "B1 (Intermedio)", "B2 (Intermedio Alto)", "C1 (Avanzado)", "C2 (Maestría)"]
        nivel_usuario_bd = user_active['nivel_calculado']
        idx_defecto = lista_niveles.index(nivel_usuario_bd) if nivel_usuario_bd in lista_niveles else 0

        level = st.sidebar.selectbox("Nivel del test (MCER)", lista_niveles, index=idx_defecto)
        num_questions = st.sidebar.slider("Número de preguntas", min_value=3, max_value=10, value=5)

        if "current_level" not in st.session_state:
            st.session_state.current_level = level

        if st.session_state.current_level != level:
            st.session_state.questions = None
            st.session_state.current_level = level

        st.title("🇬🇧 Test de Inglés Adaptativo")
        st.write(f"Hola de nuevo, **{user_active['nombre']}**. Tu nivel base actual registrado es: **{user_active['nivel_calculado']}**.")

        def generate_questions_from_api(api_key, dni, lvl, num):
            client = OpenAI(api_key=api_key)
            past_failures = get_recent_failures(dni, lvl)
            failures_context = ""
            
            if past_failures:
                failures_context = "\n⚠️ ENFOQUE ADAPTATIVO REQUERIDO:\nEl usuario ha fallado recientemente en estas preguntas. Analiza los errores y genera preguntas NUEVAS sobre los mismos conceptos gramaticales en contextos diferentes:\n"
                for f in past_failures:
                    failures_context += f"- Fallada: '{f['question']}' (Correcta era: '{f['correct_answer']}'). Regla: {f['explanation']}\n"

            prompt = f"""
            Eres un profesor de inglés experto. Genera exactamente {num} preguntas de opción múltiple adaptadas al nivel {lvl}.
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
                st.error(f"Error al conectar con OpenAI: {e}")
                return None

        if not api_key:
            st.warning("🔑 Por favor, introduce tu OpenAI API Key en la barra lateral para comenzar.")
        else:
            if st.sidebar.button("🔄 Generar Nuevo Test") or st.session_state.questions is None:
                with st.spinner("La IA está analizizando tu historial y diseñando tus preguntas..."):
                    st.session_state.questions = generate_questions_from_api(api_key, user_active['dni'], level, num_questions)
                    st.rerun()

        if st.session_state.questions:
            failures_count = len(get_recent_failures(user_active['dni'], level))
            if failures_count > 0:
                st.caption(f"🔄 Se han detectado fallos previos en el nivel {level}. Este test incluye preguntas de refuerzo personalizadas.")
            
            with st.form("quiz_form"):
                user_answers = {}
                for q in st.session_state.questions:
                    st.markdown(f"### Pregunta {q['id']}")
                    user_answers[q["id"]] = st.radio(q["question"], options=q["options"], index=None, key=f"q_{level}_{q['id']}")
                    st.write("---")
                    
                submitted = st.form_submit_button("Enviar Respuestas")

            if submitted:
                if None in user_answers.values():
                    st.warning("⚠️ Por favor, responde a todas las preguntas.")
                else:
                    score = 0
                    st.header("📊 Resultados del Test")
                    
                    with st.spinner("Guardando resultados..."):
                        for q in st.session_state.questions:
                            ans = user_answers[q["id"]]
                            is_correct = (ans == q["correct"])
                            
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
                                st.error(f"**Pregunta {q['id']}: Incorrecta**  \n*{q['question']}*  \n❌ Tu respuesta: `{ans}`  \n✅ Correcta: `{q['correct']}`")
                            
                            st.info(f"💡 **Explicación:** {q['explanation']}")
                            st.write("")
                    
                    total = len(st.session_state.questions)
                    st.subheader(f"Tu puntuación final: {score} / {total}")
                    
                    if score == total:
                        st.balloons()
                        st.success("🏆 ¡Excelente! Rendimiento perfecto.")
                    else:
                        st.warning("📝 Los fallos se han registrado en tu perfil para el próximo test.")
