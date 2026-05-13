import streamlit as st
import yt_dlp
import re
import os

st.set_page_config(page_title="YT Manager & Downloader", page_icon="📥", layout="wide")

DOWNLOAD_DIR = os.path.join(os.getcwd(), "descargas")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

if 'video_queue' not in st.session_state:
    st.session_state.video_queue = []
if 'downloading' not in st.session_state:
    st.session_state.downloading = False

def clean_filename(title):
    return re.sub(r'[\\/*?:"<>|]', "", title)

def base_ydl_opts():
    """
    Opciones base que evitan la detección de bots de YouTube automáticamente.
    - player_client: prueba android_vr y tv_embedded primero — no requieren verificación.
    - http_headers: simula un navegador real.
    - sleep_interval_requests: evita rate-limiting con pequeñas pausas.
    """
    return {
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android_vr', 'tv_embedded', 'android', 'web'],
            }
        },
        'http_headers': {
            'User-Agent': (
                'Mozilla/5.0 (Linux; Android 10; SM-G981B) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Mobile Safari/537.36'
            ),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },
        'sleep_interval_requests': 1,
        'retries': 5,
        'fragment_retries': 5,
    }

def get_video_info(url):
    ydl_opts = {**base_ydl_opts(), 'skip_download': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if 'entries' in info:
            return list(info['entries'])
        return [info]

def build_ydl_opts(video_type, quality, output_path):
    outtmpl = os.path.join(output_path, '%(title)s.%(ext)s')
    opts = {**base_ydl_opts(), 'outtmpl': outtmpl}

    if video_type == 'Audio 🎵':
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192' if quality == 'Alta' else '128',
        }]
    elif video_type == 'Video (Solo) 🎬':
        opts['format'] = 'bestvideo/best' if quality == 'Alta' else 'worstvideo/worst'
    else:
        opts['format'] = 'bestvideo+bestaudio/best' if quality == 'Alta' else 'worst'
        opts['merge_output_format'] = 'mp4'

    return opts

# --- UI ---
st.title(":red[▶️] YT Batch & Playlist Downloader")

with st.container(border=True):
    col_in, col_add, col_clear = st.columns([6, 2, 2])
    with col_in:
        new_url = st.text_input("URL del video o Playlist", placeholder="https://...", label_visibility="collapsed")
    with col_add:
        if st.button("➕ Añadir", use_container_width=True, type="secondary"):
            if new_url:
                try:
                    with st.spinner("Analizando URL..."):
                        entries = get_video_info(new_url)
                        added = 0
                        for entry in entries:
                            video_url = entry.get('webpage_url') or entry.get('url')
                            if video_url and video_url not in st.session_state.video_queue:
                                st.session_state.video_queue.append(video_url)
                                added += 1
                        if added > 1:
                            st.toast(f"Añadidos {added} videos de la playlist.")
                        else:
                            st.toast("Video añadido a la cola.")
                except Exception as e:
                    st.error(f"Error al analizar la URL: {e}")
    with col_clear:
        if st.button("🗑️ Vaciar", use_container_width=True):
            st.session_state.video_queue = []
            st.rerun()

c1, c2 = st.columns(2)
with c1:
    video_type = st.selectbox("Formato", ["Audio 🎵", "Video (Solo) 🎬", "Completo 🎥"])
with c2:
    quality = st.select_slider("Calidad", options=["Baja", "Alta"])

st.divider()

status_container = st.empty()

if st.session_state.video_queue:
    st.write(f"**Cola de descargas:** {len(st.session_state.video_queue)} videos listos.")

    if st.button("🚀 Iniciar Descarga de la Cola", type="primary", use_container_width=True):
        st.session_state.downloading = True

    if st.session_state.downloading:
        total_videos = len(st.session_state.video_queue)
        general_progress = status_container.progress(0, text=f"Progreso General: 0 / {total_videos}")

        for index, url in enumerate(st.session_state.video_queue):
            try:
                with st.container(border=True):
                    info_entries = get_video_info(url)
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

                    ydl_opts = build_ydl_opts(video_type, quality, DOWNLOAD_DIR)
                    ydl_opts['progress_hooks'] = [progress_hook]

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])

                    progress_bar.empty()

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

                        st.success(f"✅ Completado: {latest_file}")
                        with open(filepath, "rb") as f:
                            st.download_button(
                                label=f"⬇️ Descargar {latest_file}",
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
        st.success("¡Toda la cola ha sido procesada!")

else:
    st.info("Añade enlaces arriba para comenzar.")

if st.session_state.video_queue and not st.session_state.downloading:
    with st.expander("Ver videos en cola", expanded=True):
        for u in st.session_state.video_queue:
            st.caption(f"🔗 {u}")