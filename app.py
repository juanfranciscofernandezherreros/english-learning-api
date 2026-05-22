import streamlit as st
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from openai import OpenAI
from datetime import datetime

# Configuración de la página
st.set_page_config(page_title="AI Adaptive English Test", page_icon="🇬🇧", layout="centered")

st.title("🇬🇧 Test de Inglés Adaptativo con PostgreSQL")
st.write("Esta app guarda tus resultados en tu base de datos local y genera nuevas preguntas basadas en tus fallos anteriores.")

# 1. Configuración de conexiones (Traducido de tus propiedades de Spring)
DB_CONFIG = {
    "host": "ep-old-field-ambx94k5-pooler.c-5.us-east-1.aws.neon.tech",
    "port": 5432,  # El puerto estándar de PostgreSQL, implícito en la URL
    "database": "neondb",
    "user": "neondb_owner",
    "password": "npg_urVnAFP3Hy4M"
}

postgresql://neondb_owner:npg_urVnAFP3Hy4M@ep-old-field-ambx94k5-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require


# Conexión lateral para la API de OpenAI
st.sidebar.header("Configuración de la IA")
api_key = st.sidebar.text_input("Introduce tu OpenAI API Key", type="password")

level = st.sidebar.selectbox(
    "Nivel del test (MCER)", 
    ["A1 (Principiante)", "A2 (Elemental)", "B1 (Intermedio)", "B2 (Intermedio Alto)", "C1 (Avanzado)", "C2 (Maestría)"]
)
num_questions = st.sidebar.slider("Número de preguntas", min_value=3, max_value=10, value=5)

# 2. Funciones de Base de Datos
def init_db():
    """Crea la tabla de historial si no existe en invoice_db"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS english_test_history (
                id SERIAL PRIMARY KEY,
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

def save_answer_to_db(question, lvl, user_ans, correct_ans, is_correct, explanation):
    """Guarda cada respuesta del formulario en PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO english_test_history (question, level, user_answer, correct_answer, is_correct, explanation)
            VALUES (%s, %s, %s, %s, %s, %s);
        """, (question, lvl, user_ans, correct_ans, is_correct, explanation))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"Error al guardar en la base de datos: {e}")

def get_recent_failures(lvl, limit=5):
    """Recupera los últimos fallos del usuario en el nivel seleccionado"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        # Usamos RealDictCursor para manejar los resultados como diccionarios cómodamente
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT question, correct_answer, explanation 
            FROM english_test_history 
            WHERE level = %s AND is_correct = FALSE 
            ORDER BY created_at DESC 
            LIMIT %s;
        """, (lvl, limit))
        failures = cur.fetchall()
        cur.close()
        conn.close()
        return failures
    except Exception as e:
        st.error(f"Error al consultar fallos previos: {e}")
        return []

# Inicializar la base de datos al cargar la app
init_db()

# 3. Inicializar estados de la sesión de Streamlit
if "questions" not in st.session_state:
    st.session_state.questions = None
if "current_level" not in st.session_state:
    st.session_state.current_level = level

if st.session_state.current_level != level:
    st.session_state.questions = None
    st.session_state.current_level = level

# 4. Función de generación con enfoque adaptativo (Prompt dinámico)
def generate_questions_from_api(api_key, lvl, num):
    client = OpenAI(api_key=api_key)
    
    # Consultar si el usuario tiene errores previos en este nivel
    past_failures = get_recent_failures(lvl)
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

# 5. Lógica de la Interfaz
if not api_key:
    st.warning("🔑 Por favor, introduce tu OpenAI API Key en la barra lateral para comenzar.")
else:
    if st.sidebar.button("🔄 Generar Nuevo Test") or st.session_state.questions is None:
        with st.spinner("La IA está analizando tu historial y diseñando tus preguntas..."):
            st.session_state.questions = generate_questions_from_api(api_key, level, num_questions)
            st.rerun()

if st.session_state.questions:
    # Mostrar si hay preguntas de refuerzo activas
    failures_count = len(get_recent_failures(level))
    if failures_count > 0:
        st.caption(f"🔄 Se han detectado fallos previos en el nivel {level}. Este test incluye preguntas de refuerzo personalizadas.")
    
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

    # 6. Procesamiento y guardado tras enviar
    if submitted:
        if None in user_answers.values():
            st.warning("⚠️ Por favor, responde a todas las preguntas antes de enviar.")
        else:
            score = 0
            st.header("📊 Resultados del Test")
            
            with st.spinner("Guardando resultados en tu base de datos PostgreSQL..."):
                for q in st.session_state.questions:
                    ans = user_answers[q["id"]]
                    is_correct = (ans == q["correct"])
                    
                    # GUARDAR EN POSTGRESQL
                    save_answer_to_db(
                        question=q["question"],
                        lvl=level,
                        user_ans=ans,
                        correct_ans=q["correct"],
                        is_correct=is_correct,
                        explanation=q["explanation"]
                    )
                    
                    # Mostrar feedback visual inmediato en la UI
                    if is_correct:
                        score += 1
                        st.success(f"**Pregunta {q['id']}: ¡Correcta!**  \n*{q['question']}*  \n👉 Seleccionaste: `{ans}`")
                    else:
                        st.error(f"**Pregunta {q['id']}: Incorrecta (Guardada para repaso)**  \n*{q['question']}*  \n❌ Tu respuesta: `{ans}`  \n✅ Correcta: `{q['correct']}`")
                    
                    st.info(f"💡 **Explicación:** {q['explanation']}")
                    st.write("")
            
            # Puntuación final
            total = len(st.session_state.questions)
            st.subheader(f"Tu puntuación final: {score} / {total}")
            
            if score == total:
                st.balloons()
                st.success("🏆 ¡Excelente! Rendimiento perfecto.")
            else:
                st.warning("📝 Los fallos se han registrado. La próxima vez que generes un test en este nivel, la IA te preguntará sobre estos conceptos.")
