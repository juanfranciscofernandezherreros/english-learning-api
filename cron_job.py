# cron_job.py
import os
import json
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

def init_cron_tables():
    """Asegura que la infraestructura de la tabla de control exista si no ha sido creada."""
    print("🛡️  Comprobando la integridad de las tablas en Neon...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        # Crea la tabla vacía si no existe. No se inserta ningún dato automático.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS curated_topics_queue (
                id SERIAL PRIMARY KEY,
                title VARCHAR(100) UNIQUE NOT NULL,
                is_generated BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        print("✅ Estructura de tabla de control verificada.")
            
    except Exception as e:
        print(f"❌ Error crítico al inicializar las tablas del cron: {str(e)}")
    finally:
        cur.close()
        conn.close()


def generate_daily_fce_grammar_topic():
    """Busca el siguiente tema pendiente en la lista y obliga a la IA a redactar una lección magistral extensa."""
    print("🚀 Iniciando pipeline de redacción profunda para B2 First (FCE)...")
    
    # 1. Validar la clave de OpenAI desde el entorno de Heroku
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("❌ Error: OPENAI_API_KEY no está configurada en las variables de entorno de Heroku.")
        return

    # 2. Extraer el siguiente renglón pendiente de la tabla de control
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

    # 3. Control de parada segura si el temario se agota o está vacío
    if not target_topic:
        print("☕ La cola de temas está vacía o todos los temas ya han sido generados. Agrega más filas a 'curated_topics_queue'.")
        cur.close()
        conn.close()
        return

    tema_id = target_topic['id']
    tema_titulo = target_topic['title']
    print(f"🎯 Fila detectada. Redactando lección magistral para el tema: '{tema_titulo}'")

    # 4. Construir la llamada estructurada a OpenAI
    client = OpenAI(api_key=openai_api_key)
    
    prompt_generacion = f"""
    Eres un profesor de inglés nativo, extremadamente carismático, empático y experto en preparar a estudiantes para el examen oficial Cambridge B2 First Certificate (FCE). 
    Tu tono es muy cercano, motivador, claro y pedagógico, como si estuvieras dictando una clase maestra en vivo en una pizarra. Te apasiona enseñar y tu meta es que el alumno entienda la lógica profunda detrás de las reglas.

    Tu tarea es escribir un artículo EXTENSO, sumamente minucioso y ultra detallado sobre el siguiente concepto técnico:
    TEMA: '{tema_titulo}'

    INSTRUCCIONES DE REDACCIÓN (Sé muy generoso con el texto, no escatimes en detalles ni resumas):
    1. EXPLICACIÓN PROFUNDA: Desglosa el tema desde cero. Explica detalladamente las fórmulas estructurales, los matices de significado y en qué contextos exactos se debe emplear frente a otras estructuras alternativas.
    2. ENFOQUE EXAMEN (Use of English): Explica de forma explícita y práctica cómo utiliza Cambridge este punto gramatical exacto para puntuar o penalizar en las partes 2, 3 y 4 del examen.
    3. TRUCOS Y TRAMPAS (Cambridge Traps / FCE Tips): Actúa como un verdadero mentor. Advierte al alumno sobre los errores más comunes que comete el 90% de los estudiantes hispanohablantes debido a la traducción literal y revélale los trucos específicos que usa Cambridge para poner trampas en el examen real.

    Devuelve un objeto JSON estricto que contenga las siguientes claves directamente en la RAÍZ (nivel superior) del objeto:
    {{
        "title": "{tema_titulo}",
        "summary": "Un gancho corto, enérgico y motivador en español que explique qué superpoder gramatical ganará el alumno hoy para destruir su examen B2.",
        "content": "Escribe aquí la lección completa en español utilizando tu voz de profesor experto. Utiliza subtítulos con Markdown (## y ###) y viñetas bien organizadas. Extiéndete con total libertad para asegurar una explicación impecable, profunda y de nivel académico premium.",
        "examples": [
            "Debes incluir de forma obligatoria entre 8 y 10 ejemplos detallados en formato string. Al menos 4 de ellos deben ser transformaciones reales tipo 'Use of English Part 4'. Organiza cada ejemplo de forma visualmente clara siguiendo este patrón exacto: 'ORIGINAL: [frase] | KEYWORD: [palabra] | TRANSFORMED: [resultado] (Traducción al español)'."
        ]
    }}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt_generacion}],
            response_format={"type": "json_object"},
            temperature=0.5
        )

        nuevo_tema = json.loads(response.choices[0].message.content)

        # 5. Insertar el contenido y marcar el tema como procesado en la misma transacción
        cur.close()
        cur = conn.cursor()

        # Inyección en la biblioteca de temas finales
        cur.execute("""
            INSERT INTO learning_topics (title, summary, content, examples)
            VALUES (%s, %s, %s, %s);
        """, (
            nuevo_tema["title"],
            nuevo_tema["summary"],
            nuevo_tema["content"],
            json.dumps(nuevo_tema["examples"])
        ))

        # Actualización de la fila en la tabla de control
        cur.execute("""
            UPDATE curated_topics_queue 
            SET is_generated = TRUE 
            WHERE id = %s;
        """, (tema_id,))

        conn.commit()
        print(f"✅ ¡Lección magistral publicada con éxito! Tema: '{nuevo_tema['title']}' listo para estudio.")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error en la generación y transacción del artículo: {str(e)}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    # 1. Asegurar la existencia de la estructura base
    init_cron_tables()
    
    # 2. Ejecutar la lectura y generación del tema pendiente
    generate_daily_fce_grammar_topic()
