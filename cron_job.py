# cron_job.py
import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from openai import OpenAI

DB_CONFIG = {
    "host": "ep-old-field-ambx94k5-pooler.c-5.us-east-1.aws.neon.tech",
    "port": 5432,
    "database": "neondb",
    "user": "neondb_owner",
    "password": "npg_urVnAFP3Hy4M"
}

def generate_daily_fce_grammar_topic():
    print("🚀 Iniciando generador secuencial profundo para B2 First (FCE)...")
    
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("❌ Error: OPENAI_API_KEY no está configurada en Heroku.")
        return

    # --- PASO 1: LEER EL SIGUIENTE TEMA PENDIENTE DE LA COLA ---
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("""
            SELECT id, title FROM curated_topics_queue 
            WHERE is_generated = FALSE 
            ORDER BY id ASC LIMIT 1;
        """)
        target_topic = cur.fetchone()
    except Exception as e:
        print(f"❌ Error al consultar la cola de temas: {str(e)}")
        cur.close()
        conn.close()
        return

    if not target_topic:
        print("☕ Todos los temas de la lista ya han sido generados.")
        cur.close()
        conn.close()
        return

    tema_id = target_topic['id']
    tema_titulo = target_topic['title']
    print(f"🎯 Redactando lección magistral para: '{tema_titulo}'")

    # --- PASO 2: ENVIAR A OPENAI CON EL PROMPT DE PROFESOR EXPERTO ---
    client = OpenAI(api_key=openai_api_key)
    
    prompt_generacion = f"""
    Eres un profesor de inglés nativo, carismático, empático y experto en preparar a alumnos para el examen Cambridge B2 First Certificate (FCE). 
    Tu tono es cercano, motivador, claro y muy pedagógico, como si estuvieras dando una clase en directo. Te apasiona enseñar y quieres que el alumno realmente 'entienda' el porqué de las reglas, no que solo las memorice.

    Tu tarea es escribir un artículo EXTENSO, minucioso y ultra detallado sobre el siguiente tema:
    TEMA: '{tema_titulo}'

    INSTRUCCIONES DE REDACCIÓN (Sé muy generoso con el texto, no resumas):
    1. EXPLICACIÓN PROFUNDA: Desglosa el tema desde cero. Explica las fórmulas físicas estructurales, los matices de significado y en qué situaciones exactas se usa frente a otras estructuras parecidas.
    2. ENFOQUE EXAMEN (Use of English): Explica de forma explícita cómo utiliza Cambridge este punto gramatical para puntuar o penalizar en las partes 2, 3 y 4 del examen.
    3. TRUCOS Y TRAMPAS (Cambridge Traps): Actúa como un mentor. Advierte al alumno sobre los errores típicos que comete el 90% de los estudiantes hispanohablantes y revélale los trucos que usa Cambridge para poner trampas en el examen real.

    Devuelve un objeto JSON estricto con la clave 'topic':
    {{
        "title": "{tema_titulo}",
        "summary": "Un gancho corto y motivador en español que explique qué superpoder gramatical ganará el alumno hoy para su examen B2.",
        "content": "Escribe aquí la lección completa en español utilizando un formato de profesor (puedes usar subtítulos internos y viñetas organizadas). Extiéndete todo lo necesario para que sea una explicación impecable, profunda y de nivel académico premium.",
        "examples": [
            "Debes incluir obligatoriamente entre 8 y 10 ejemplos detallados en formato string. Combina oraciones de uso común con al menos 4 transformaciones reales tipo 'Use of English Part 4'. Organiza cada ejemplo de forma visualmente clara, por ejemplo: 'ORIGINAL: ... | KEYWORD: ... | TRANSFORMED: ... (Traducción al español)'."
        ]
    }}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt_generacion}],
            response_format={"type": "json_object"},
            temperature=0.5 # Equilibrio: creativo en el tono de profesor, riguroso en la gramática
        )

        datos_respuesta = json.loads(response.choices[0].message.content)
        nuevo_tema = datos_respuesta["topic"]

        # --- PASO 3: GUARDAR CONTENIDO Y ACTUALIZAR ESTADO ---
        cur.close()
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

        cur.execute("""
            UPDATE curated_topics_queue 
            SET is_generated = TRUE 
            WHERE id = %s;
        """, (tema_id,))

        conn.commit()
        print(f"✅ ¡Lección magistral publicada con éxito!: {nuevo_tema['title']}")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error en la generación del artículo extenso: {str(e)}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    generate_daily_fce_grammar_topic()
