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

        # 2. Seguro por límite de temas (un curso B2 completo suele rondar las 30 unidades)
        if len(existing_topics) >= 100 :
            print("🏁 El currículo B2 ya ha alcanzado el límite de 100 temas. Se considera completo.")
            return

        # 3. Prompt de nivel Director de Estudios Cambridge
        prompt = f"""
        Eres el Director de Estudios de una academia de élite especializada en preparar el examen Cambridge B2 First (FCE).
        Estamos construyendo el temario dinámico del curso. Un curso completo de FCE tiene un máximo de 100 unidades.
        
        Este es el temario que ya hemos generado hasta ahora, en estricto orden:
        {existing_topics}

        Tu tarea:
        Analiza los temas existentes y decide cuál es LA SIGUIENTE UNIDAD lógica. 
        Un temario B2 de calidad no solo tiene Gramática. Debes alternar y asegurar que a lo largo del curso se cubran:
        - Gramática avanzada B2 (Modals, Conditionals, Relatives, Passives, Inversion, etc.).
        - Use of English (Técnicas para Part 1 Multiple Choice, Part 2 Open Cloze, Part 3 Word Formation, Part 4 Transformations).
        - Reading (Estrategias para Parts 5, 6 y 7).
        - Writing (Estructura, linking words y vocabulario para Part 1 Essay, y Part 2 Article, Review, Report, Email/Letter).
        - Vocabulario clave (Phrasal verbs por temáticas, Collocations, False Friends).

        REGLAS:
        1. Si consideras que el temario actual YA CUBRE todo lo necesario para aprobar el B2 First con buena nota, devuelve exactamente este valor en el título: "COMPLETE".
        2. Si aún falta temario, genera el título del siguiente tema alternando habilidades. Por ejemplo, si los últimos dos fueron de gramática, el siguiente DEBE ser de Use of English o Writing.
        3. Devuelve un JSON estricto con una única clave "title".
        
        Ejemplos de buenos títulos:
        - "Unit 7: Grammar - Mixed Conditionals and Wish/If Only"
        - "Unit 8: Use of English Part 3 - Word Formation (Prefixes & Suffixes)"
        - "Unit 9: Writing Part 1 - How to structure a perfect B2 Essay"
        - "Unit 10: Vocabulary - Essential Phrasal Verbs with GET and TAKE"
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.4
        )
        
        data = json.loads(response.choices[0].message.content)
        next_title = data.get("title", "")

        # 4. Verificar si la IA ha decidido que el curso ya está completo
        if next_title == "COMPLETE" or next_title.upper() == "COMPLETE":
            print("🏁 OpenAI ha determinado que el currículo B2 FCE está 100% completo. No se añadirán más temas.")
            return

        # 5. Si no está completo, insertamos el nuevo tema en la base de datos
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
