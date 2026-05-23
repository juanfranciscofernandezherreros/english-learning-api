
# cron_job.py
import os
import json
import psycopg2
from openai import OpenAI

# Configuración (Idealmente pasa esto a Config Vars en Heroku)
DB_CONFIG = {
    "host": "ep-old-field-ambx94k5-pooler.c-5.us-east-1.aws.neon.tech",
    "port": 5432,
    "database": "neondb",
    "user": "neondb_owner",
    "password": "npg_urVnAFP3Hy4M"
}

def generate_daily_lifestyle_topic():
    print("🚀 Iniciando generador diario de tópicos situacionales...")
    
    # 1. Leer la API Key de OpenAI desde las variables de Heroku
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("❌ Error: OPENAI_API_KEY no está configurada en Heroku.")
        return

    # 2. Consultar temas actuales en Neon
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        cur.execute("SELECT title FROM learning_topics;")
        temas_actuales = [row[0] for row in cur.fetchall()]
    finally:
        cur.close()

    # 3. Conectar con OpenAI
    client = OpenAI(api_key=openai_api_key)
    prompt = f"""
    Eres un diseñador de cursos de inglés enfocado en el "Método Inmersivo y Cotidiano". 
    Tu objetivo es crear una lección basada estrictamente en una situación del día a día (Life Skills / Everyday English).

    SITUACIONES YA CUBIERTAS (No las repitas bajo ningún concepto):
    {json.dumps(temas_actuales)}

    INSTRUCCIONES:
    1. Elige una nueva situación real cotidiana (ej: pedir indicaciones en la calle, ir al médico, una reunión de vecinos, etc.).
    2. Devuelve un objeto JSON estricto con la clave "topic" estructurado así:
    {{
        "title": "Título atractivo en español y contexto en inglés (ej: 'En el Supermercado: Grocery Shopping')",
        "summary": "Resumen corto en español de lo que el alumno sabrá resolver hoy.",
        "content": "Explicación didáctica en español con: 1) Frases clave (Key Phrases). 2) Vocabulario esencial. 3) Una mini-regla gramatical simple adaptada a la situación.",
        "examples": ["Mínimo 3 diálogos cortos reales en inglés con su traducción al lado."]
    }}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        
        datos_respuesta = json.loads(response.choices[0].message.content)
        nuevo_tema = datos_respuesta["topic"]

        # 4. Insertar el nuevo tema en Neon
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
        print(f"✅ ¡Tema generado e insertado con éxito!: {nuevo_tema['title']}")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error durante la ejecución: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":
    generate_daily_lifestyle_topic()
