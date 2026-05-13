import streamlit as st
import yt_dlp
import re
import os
import tempfile

st.set_page_config(page_title="YT Manager & Downloader", page_icon="ðŸ“¥", layout="wide")

# --- Directorio de descargas ---
DOWNLOAD_DIR = os.path.join(os.getcwd(), "descargas")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- InicializaciÃ³n del Estado ---
if 'video_queue' not in st.session_state:
    st.session_state.video_queue = []
if 'downloading' not in st.session_state:
    st.session_state.downloading = False
if 'cookies_path' not in st.session_state:
    st.session_state.cookies_path = None

def clean_filename(title):
    return re.sub(r'[\\/*?:"<>|]', "", title)

def base_ydl_opts(cookies_path=None):
    """Common options shared by all yt-dlp calls: headers, retries, cookies."""
    opts = {
        'quiet': True,
        'no_warnings': True,
        # Mimic a real browser to reduce bot-detection false positives
        'http_headers': {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            'Accept-Language': 'en-US,en;q=0.9',
        },
        # Use the Android client which is less restricted than web
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
            }
        },
        'retries': 3,
        'fragment_retries': 3,
    }
    if cookies_path:
        opts['cookiefile'] = cookies_path
    return opts

def get_video_info(url, cookies_path=None):
    """Obtiene tÃ­tulo y thumbnail sin descargar."""
    ydl_opts = {
        **base_ydl_opts(cookies_path),
        'skip_download': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if 'entries' in info:
            return list(info['entries'])
        return [info]

def build_ydl_opts(video_type, quality, output_path, cookies_path=None):
    """Construye las opciones de yt-dlp segÃºn formato y calidad."""
    outtmpl = os.path.join(output_path, '%(title)s.%(ext)s')
    opts = base_ydl_opts(cookies_path)
    opts['outtmpl'] = outtmpl

    if video_type == 'Audio ðŸŽµ':
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192' if quality == 'Alta' else '128',
        }]
    elif video_type == 'Video (Solo) ðŸŽ¬':
        opts['format'] = 'bestvideo/best' if quality == 'Alta' else 'worstvideo/worst'
    else:  # Completo
        opts['format'] = 'bestvideo+bestaudio/best' if quality == 'Alta' else 'worst'
        opts['merge_output_format'] = 'mp4'

    return opts

# --- Interfaz Principal ---
st.title(":red[â–¶ï¸] YT Batch & Playlist Downloader")

# --- Cookie Upload (sidebar) ---
with st.sidebar:
    st.header("ðŸ” AutenticaciÃ³n (Opcional)")
    st.markdown(
        "Si YouTube bloquea las descargas con el error **'Sign in to confirm'**, "
        "sube aquÃ­ tu archivo `cookies.txt` exportado desde el navegador."
    )

    uploaded_cookies = st.file_uploader(
        "Subir cookies.txt",
        type=["txt"],
        help="Exporta las cookies de youtube.com con la extensiÃ³n 'Get cookies.txt LOCALLY' (Chrome/Firefox).",
    )

    if uploaded_cookies is not None:
        # Save to a temp file that persists for the session
        if st.session_state.cookies_path is None or not os.path.exists(st.session_state.cookies_path):
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="wb")
            tmp.write(uploaded_cookies.read())
            tmp.flush()
            tmp.close()
            st.session_state.cookies_path = tmp.name
        st.success("âœ… Cookies cargadas correctamente.")
    else:
        # Clean up old temp file if user removed the upload
        if st.session_state.cookies_path and os.path.exists(st.session_state.cookies_path):
            os.unlink(st.session_state.cookies_path)
        st.session_state.cookies_path = None
        st.info("Sin cookies â€” se usarÃ¡n opciones de bypass automÃ¡tico.")

    st.divider()
    st.markdown(
        "**Â¿CÃ³mo exportar cookies?**\n\n"
        "1. Instala [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)\n"
        "2. Inicia sesiÃ³n en youtube.com\n"
        "3. Haz clic en la extensiÃ³n â†’ *Export* â†’ guarda el fichero\n"
        "4. SÃºbelo aquÃ­ â˜ï¸"
    )

cookies_path = st.session_state.cookies_path

# --- URL Input ---
with st.container(border=True):
    col_in, col_add, col_clear = st.columns([6, 2, 2])
    with col_in:
        new_url = st.text_input("URL del video o Playlist", placeholder="https://...", label_visibility="collapsed")
    with col_add:
        if st.button("âž• AÃ±adir", use_container_width=True, type="secondary"):
            if new_url:
                try:
                    with st.spinner("Analizando URL..."):
                        entries = get_video_info(new_url, cookies_path)
                        added = 0
                        for entry in entries:
                            video_url = entry.get('webpage_url') or entry.get('url')
                            if video_url and video_url not in st.session_state.video_queue:
                                st.session_state.video_queue.append(video_url)
                                added += 1
                        if added > 1:
                            st.toast(f"AÃ±adidos {added} videos de la playlist.")
                        else:
                            st.toast("Video aÃ±adido a la cola.")
                except Exception as e:
                    st.error(f"Error al analizar la URL: {e}")
    with col_clear:
        if st.button("ðŸ—‘ï¸ Vaciar", use_container_width=True):
            st.session_state.video_queue = []
            st.rerun()

# Ajustes globales
c1, c2 = st.columns(2)
with c1:
    video_type = st.selectbox("Formato", ["Audio ðŸŽµ", "Video (Solo) ðŸŽ¬", "Completo ðŸŽ¥"])
with c2:
    quality = st.select_slider("Calidad", options=["Baja", "Alta"])

st.divider()

# --- LÃ³gica de Descarga ---
status_container = st.empty()

if st.session_state.video_queue:
    st.write(f"**Cola de descargas:** {len(st.session_state.video_queue)} videos listos.")

    if st.button("ðŸš€ Iniciar Descarga de la Cola", type="primary", use_container_width=True):
        st.session_state.downloading = True

    if st.session_state.downloading:
        total_videos = len(st.session_state.video_queue)
        general_progress = status_container.progress(0, text=f"Progreso General: 0 / {total_videos}")

        for index, url in enumerate(st.session_state.video_queue):
            try:
                with st.container(border=True):
                    info_entries = get_video_info(url, cookies_path)
                    info = info_entries[0]
                    title = info.get('title', 'video')
                    thumbnail = info.get('thumbnail')

                    col_t, col_i = st.columns([1, 4])
                    with col_t:
                        if thumbnail:
                            st.image(thumbnail, width=150)
                    with col_i:
                        st.markdown(f"**{title}**")

                    progress_bar = st.progress(0, text="Preparando descarga...")

                    def progress_hook(d):
                        if d['status'] == 'downloading':
                            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                            downloaded = d.get('downloaded_bytes', 0)
                            if total > 0:
                                pct = int(downloaded / total * 100)
                                progress_bar.progress(pct, text=f"Descargando: {pct}%")
                        elif d['status'] == 'finished':
                            progress_bar.progress(100, text="Procesando...")

                    ydl_opts = build_ydl_opts(video_type, quality, DOWNLOAD_DIR, cookies_path)
                    ydl_opts['progress_hooks'] = [progress_hook]

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])

                    progress_bar.empty()

                    # Buscar el archivo generado mÃ¡s reciente
                    files = sorted(
                        [f for f in os.listdir(DOWNLOAD_DIR)],
                        key=lambda f: os.path.getmtime(os.path.join(DOWNLOAD_DIR, f)),
                        reverse=True
                    )

                    if files:
                        latest_file = files[0]
                        filepath = os.path.join(DOWNLOAD_DIR, latest_file)
                        ext = latest_file.rsplit('.', 1)[-1]
                        mime = "audio/mpeg" if ext == "mp3" else "video/mp4"

                        st.success(f"âœ… Completado: {latest_file}")
                        with open(filepath, "rb") as f:
                            st.download_button(
                                label=f"â¬‡ï¸ Descargar {latest_file}",
                                data=f,
                                file_name=latest_file,
                                mime=mime,
                                key=f"dl_{index}",
                            )

            except Exception as e:
                st.error(f"Fallo al descargar {url}: {e}")

            current_progress = int(((index + 1) / total_videos) * 100)
            general_progress.progress(current_progress, text=f"Progreso General: {index + 1} / {total_videos}")

        st.session_state.downloading = False
        st.balloons()
        st.success("Â¡Toda la cola ha sido procesada!")

else:
    st.info("AÃ±ade enlaces arriba para comenzar.")

# --- Vista previa de la cola ---
if st.session_state.video_queue and not st.session_state.downloading:
    with st.expander("Ver videos en cola", expanded=True):
        for u in st.session_state.video_queue:
            st.caption(f"ðŸ”— {u}")