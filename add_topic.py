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

def auto_generate_next_topic():
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("❌ Error: OPENAI_API_KEY no configurada.")
        return

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    client = OpenAI(api_key=openai_api_key)

    try:
        # 1. Leer todos los temas que ya existen en la base de datos
        cur.execute("SELECT title FROM curated_topics_queue ORDER BY id ASC;")
        existing_topics = [row[0] for row in cur.fetchall()]

        # 2. Decidir el siguiente tema
        if not existing_topics:
            # Si la tabla está vacía, empezamos por el principio
            next_title = "Unit 1: Present Tenses (Simple, Continuous, State Verbs)"
        else:
            # Si ya hay temas, le pedimos a OpenAI que calcule el siguiente
            prompt = f"""
            Eres el jefe de estudios de una academia preparadora del examen Cambridge B2 First (FCE).
            Este es el temario que ya hemos generado hasta ahora, en orden:
            {existing_topics}

            Tu tarea es decidir cuál es el SIGUIENTE tema gramatical o de vocabulario que los alumnos deben aprender, siguiendo una progresión lógica para el B2.
            Devuelve un JSON estricto con una única clave "title", siguiendo el formato "Unit [Número siguiente]: [Nombre del tema]".
            """

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
            data = json.loads(response.choices[0].message.content)
            next_title = data["title"]

        # 3. Guardar el nuevo tema en la cola para que cron_job.py lo procese luego
        cur.execute("INSERT INTO curated_topics_queue (title, is_generated) VALUES (%s, FALSE);", (next_title,))
        conn.commit()
        print(f"✅ OpenAI ha decidido y añadido el siguiente tema a la cola: '{next_title}'")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error al generar el siguiente tema: {str(e)}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    auto_generate_next_topic()
