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
    print("🛡️ Comprobando la integridad de las tablas...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS curated_topics_queue (
                id SERIAL PRIMARY KEY,
                title VARCHAR(100) UNIQUE NOT NULL,
                is_generated BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    except Exception as e:
        print(f"❌ Error al inicializar tablas: {str(e)}")
    finally:
        cur.close()
        conn.close()

def generate_all_pending_topics():
    print("🚀 Iniciando pipeline masivo...")
    
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("❌ Error: OPENAI_API_KEY no configurada.")
        return

    conn = psycopg2.connect(**DB_CONFIG)
    client = OpenAI(api_key=openai_api_key)
    
    # BUCLE: Procesar mientras haya temas pendientes
    while True:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, title FROM curated_topics_queue WHERE is_generated = FALSE ORDER BY id ASC LIMIT 1;")
        target = cur.fetchone()
        cur.close()

        if not target:
            print("☕ Cola vacía. Proceso finalizado.")
            break

        tema_id = target['id']
        tema_titulo = target['title']
        print(f"🎯 Generando: '{tema_titulo}' (ID: {tema_id})")

        prompt = f"""
        Eres un profesor de inglés nativo experto en Cambridge B2 First (FCE). 
        Escribe una lección EXTENSA y detallada sobre: '{tema_titulo}'.
        Incluye explicaciones profundas, trucos para el examen (Cambridge Traps) y ejemplos prácticos.
        Devuelve un JSON estricto con claves: "title", "summary", "content" (Markdown), "examples" (Array de strings tipo 'ORIGINAL: ... | KEYWORD: ... | TRANSFORMED: ...').
        """

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.5
            )
            data = json.loads(response.choices[0].message.content)

            cur = conn.cursor()
            # Guardar lección
            cur.execute("""
                INSERT INTO learning_topics (title, summary, content, examples)
                VALUES (%s, %s, %s, %s);
            """, (data["title"], data["summary"], data["content"], json.dumps(data["examples"])))

            # Marcar como generado
            cur.execute("UPDATE curated_topics_queue SET is_generated = TRUE WHERE id = %s;", (tema_id,))
            conn.commit()
            cur.close()
            print(f"✅ Éxito: {tema_titulo}")

        except Exception as e:
            conn.rollback()
            print(f"❌ Error en tema {tema_titulo}: {str(e)}")
            break # Rompemos por seguridad si hay un error persistente

    conn.close()

if __name__ == "__main__":
    init_cron_tables()
    generate_all_pending_topics()
