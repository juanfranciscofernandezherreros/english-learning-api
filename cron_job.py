# cron_job.py
import os
import json
import psycopg2
from openai import OpenAI

DB_CONFIG = {
    "host": "ep-old-field-ambx94k5-pooler.c-5.us-east-1.aws.neon.tech",
    "port": 5432,
    "database": "neondb",
    "user": "neondb_owner",
    "password": "npg_urVnAFP3Hy4M"
}

def generate_daily_fce_grammar_topic():
    print("🚀 Iniciando pipeline dinámico de dos pasos para B2 First (FCE)...")
    
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("❌ Error: OPENAI_API_KEY no está configurada en Heroku.")
        return

    # --- PASO 0: LEER LO QUE YA EXISTE EN NEON ---
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        cur.execute("SELECT title FROM learning_topics;")
        temas_actuales = [row[0] for row in cur.fetchall()]
    finally:
        cur.close()

    client = OpenAI(api_key=openai_api_key)

    # --- PASO 1: DECIDIR EL TEMA (Brainstorming) ---
    print(f"📊 Analizando {len(temas_actuales)} temas existentes para decidir el siguiente paso...")
    
    prompt_decision = f"""
    Eres el Director de Estudios de una academia oficial de Cambridge. Tu única tarea es analizar el plan de estudios actual de nivel B2 First (FCE) y decidir qué concepto técnico de gramática avanzada falta por agregar.

    TEMAS QUE YA ESTÁN REGISTRADOS:
    {json.dumps(temas_actuales)}

    INSTRUCCIONES:
    Revisa la lista anterior. Pensando en el temario oficial de Cambridge B2 First (especialmente las estructuras necesarias para Use of English Parts 2, 3 y 4), determina cuál es el siguiente tema gramatical más urgente, específico y relevante que no esté en la lista. 
    Evita títulos genéricos como 'Gramática B2' o 'Tiempos Verbales'. Debe ser un punto gramatical concreto.

    Devuelve estrictamente un objeto JSON con la clave 'chosen_topic':
    {{
        "chosen_topic": "Nombre técnico exacto del tema en inglés"
    }}
    """

    try:
        response_1 = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt_decision}],
            response_format={"type": "json_object"},
            temperature=0.8 # Un poco más alto para que varíe sus decisiones de currículum
        )
        
        decision = json.loads(response_1.choices[0].message.content)
        tema_elegido = decision.get("chosen_topic")
        print(f"🎯 La IA ha decidido crear la lección: '{tema_elegido}'")

        # --- PASO 2: GENERAR EL CONTENIDO DE FORMA PROFUNDA ---
        print(f"✍️ Generando contenido académico exhaustivo para '{tema_elegido}'...")
        
        prompt_generacion = f"""
        Eres un examinador experto de Cambridge B2 First Certificate (FCE). 
        Tu tarea es redactar una lección de nivel B2 completa, rigurosa y didáctica centrada única y exclusivamente en el siguiente tema:

        TEMA A DESARROLLAR: '{tema_elegido}'

        Devuelve un objeto JSON estricto con la clave 'topic' estructurado de la siguiente forma:
        {{
            "title": "{tema_elegido}",
            "summary": "Una frase corta en español que explique qué estructura del examen B2 First o problema práctico resuelve esta lección.",
            "content": "Explicación didáctica y rigurosa en español. Debe incluir: 1) Estructura formal y fórmulas gramaticales claras. 2) Cómo se aplica exactamente en las secciones de Use of English. 3) Cambridge Traps / FCE Tips: Trucos de examen y errores típicos que los alumnos cometen y que Cambridge suele poner como trampa en el Use of English Part 4.",
            "examples": ["Mínimo 3 ejemplos reales de transformación de frases (Key Word Transformation) tipo examen B2 en inglés, incluyendo la palabra clave requerida si aplica, y su correspondiente traducción al español entre paréntesis."]
        }}
        """

        response_2 = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt_generacion}],
            response_format={"type": "json_object"},
            temperature=0.3 # Temperatura baja para máxima precisión en la teoría y fórmulas
        )

        datos_respuesta = json.loads(response_2.choices[0].message.content)
        nuevo_tema = datos_respuesta["topic"]

        # --- PASO 3: GUARDAR EN NEON ---
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO learning_topics (title, summary, content, examples)
            VALUES (%s, %s, %s, %s);
        """, (
            nuevo_tema["title"],
            nuevo_tema["summary"],
            nuevo_tema["content"],
            json.dumps(nuevo_tema["examples"])
        ))
        conn.commit()
        print(f"✅ ¡Pipeline completado con éxito! Tema insertado: {nuevo_tema['title']}")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error en el pipeline dinámico: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":
    generate_daily_fce_grammar_topic()
