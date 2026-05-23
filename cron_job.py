# cron_job.py
import os
import json
import psycopg2
from openai import OpenAI

# Configuración (Se recomienda pasar esto a Config Vars en Heroku)
DB_CONFIG = {
    "host": "ep-old-field-ambx94k5-pooler.c-5.us-east-1.aws.neon.tech",
    "port": 5432,
    "database": "neondb",
    "user": "neondb_owner",
    "password": "npg_urVnAFP3Hy4M"
}

def generate_daily_fce_grammar_topic():
    print("🚀 Iniciando generador diario de gramática B2 First (FCE)...")
    
    # 1. Leer la API Key de OpenAI desde las variables de Heroku
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("❌ Error: OPENAI_API_KEY no está configurada en Heroku.")
        return

    # 2. Consultar temas actuales en Neon para evitar duplicados
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        cur.execute("SELECT title FROM learning_topics;")
        temas_actuales = [row[0] for row in cur.fetchall()]
    finally:
        cur.close()

    # 3. Conectar con OpenAI empleando el nuevo enfoque B2 First
    client = OpenAI(api_key=openai_api_key)
    prompt = f"""
    Eres un profesor nativo y examinador experto encargado de preparar a alumnos para el examen oficial Cambridge B2 First Certificate (FCE).
    Tu objetivo es redactar una lección de gramática avanzada y específica de nivel B2 que sea crucial para superar la sección de 'Use of English' (especialmente las partes 2, 3 y 4 de transformaciones).

    TEMAS DE GRAMÁTICA YA EXISTENTES (No los repitas bajo ningún concepto):
    {json.dumps(temas_actuales)}

    INSTRUCCIONES:
    1. Elige un tema gramatical clave del temario oficial B2 First que no esté en la lista anterior.
       Ejemplos de temas válidos: Mixed Conditionals, Passive with reporting verbs (It is said that...), Inversion for emphasis (Seldom have I...), Wish & If Only, Modals of deduction in the past (must have been), Relative clauses (defining vs non-defining), Gerund vs Infinitive advanced, Used to/Get used to/Would, Phrasal Verbs cruciales para B2.
    2. Devuelve un objeto JSON estricto con la clave "topic" estructurado de la siguiente forma:
    {{
        "title": "Nombre del tema gramatical técnico en inglés (ej: 'Speculation and Deduction in the Past')",
        "summary": "Una frase corta en español que explique qué estructura del examen B2 First resuelve esta lección.",
        "content": "Explicación didáctica y rigurosa en español. Debe incluir de forma clara: 1) Estructura formal y fórmulas gramaticales. 2) Cómo se aplica exactamente en el examen B2 First. 3) Cambridge Traps / FCE Tips: Trucos esenciales y errores típicos que los alumnos cometen y que Cambridge suele poner como trampa en el Use of English Part 4.",
        "examples": ["Mínimo 3 ejemplos o estructuras de transformación tipo examen (Key Word Transformation) en inglés, con su correspondiente traducción al español entre paréntesis."]
    }}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.5 # Temperatura más baja para mantener el rigor académico del B2
        )
        
        datos_respuesta = json.loads(response.choices[0].message.content)
        nuevo_tema = datos_respuesta["topic"]

        # 4. Insertar el nuevo tema B2 en la base de datos Neon
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
        print(f"✅ Temario FCE expandido. Tema insertado: {nuevo_tema['title']}")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error durante la ejecución del temario FCE: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":
    generate_daily_fce_grammar_topic()
