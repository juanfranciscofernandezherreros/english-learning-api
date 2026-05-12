import streamlit as st
from pytubefix import YouTube, Playlist
from pytubefix.cli import on_progress
import re
import os

st.set_page_config(page_title="YT Manager & Downloader", page_icon="📥", layout="wide")

# --- Inicialización del Estado ---
if 'video_queue' not in st.session_state:
    st.session_state.video_queue = []
if 'downloading' not in st.session_state:
    st.session_state.downloading = False

def clean_filename(title):
    return re.sub(r'[\\/*?:"<>|]', "", title)

# --- Interfaz Principal ---
st.title(":red[▶️] YT Batch & Playlist Downloader")

with st.container(border=True):
    col_in, col_add, col_clear = st.columns([6, 2, 2])
    with col_in:
        new_url = st.text_input("URL del video o Playlist", placeholder="https://...", label_visibility="collapsed")
    with col_add:
        if st.button("➕ Añadir", use_container_width=True, type="secondary"):
            if new_url:
                try:
                    if "list=" in new_url:
                        with st.spinner("Cargando lista..."):
                            pl = Playlist(new_url)
                            for video_url in pl.video_urls:
                                if video_url not in st.session_state.video_queue:
                                    st.session_state.video_queue.append(video_url)
                            st.toast(f"Añadidos {len(pl.video_urls)} videos.")
                    else:
                        if new_url not in st.session_state.video_queue:
                            st.session_state.video_queue.append(new_url)
                except Exception as e:
                    st.error(f"Error: {e}")
    with col_clear:
        if st.button("🗑️ Vaciar", use_container_width=True):
            st.session_state.video_queue = []
            st.rerun()

# Ajustes globales
c1, c2 = st.columns(2)
with c1:
    video_type = st.selectbox("Formato", ["Audio 🎵", "Video (Solo) 🎬", "Completo 🎥"])
with c2:
    quality = st.select_slider("Calidad", options=["Baja", "Alta"])

st.divider()

# --- Lógica de Descarga y Progreso ---

# Contenedor para el estado general de la descarga
status_container = st.empty()

if st.session_state.video_queue:
    st.write(f"**Cola de descargas:** {len(st.session_state.video_queue)} videos listos.")
    
    # Botón maestro para iniciar la descarga secuencial
    if st.button("🚀 Iniciar Descarga de la Cola", type="primary", use_container_width=True):
        st.session_state.downloading = True

    if st.session_state.downloading:
        total_videos = len(st.session_state.video_queue)
        
        # Barra de progreso general
        general_progress = status_container.progress(0, text=f"Progreso General: 0 / {total_videos}")
        
        for index, url in enumerate(st.session_state.video_queue):
            try:
                # Contenedor visual para el video actual
                with st.container(border=True):
                    # --- Configuración del callback de progreso para Streamlit ---
                    progress_bar = st.empty()
                    
                    def progress_function(stream, chunk, bytes_remaining):
                        total_size = stream.filesize
                        bytes_downloaded = total_size - bytes_remaining
                        percentage = int(bytes_downloaded / total_size * 100)
                        # Actualizar la barra de progreso individual
                        progress_bar.progress(percentage, text=f"Descargando: {percentage}%")

                    # Instanciar YouTube con el callback
                    yt = YouTube(url, on_progress_callback=progress_function)
                    title = yt.title
                    
                    col_t, col_i = st.columns([1, 4])
                    with col_t:
                        st.image(yt.thumbnail_url, width=150)
                    with col_i:
                        st.markdown(f"**{title}**")
                        
                    # Filtrado de streams
                    if video_type == 'Audio 🎵':
                        s = yt.streams.filter(only_audio=True).order_by("abr")
                        ext = "mp3"
                    elif video_type == 'Video (Solo) 🎬':
                        s = yt.streams.filter(only_video=True).order_by("resolution")
                        ext = "mp4"
                    else:
                        s = yt.streams.filter(progressive=True).order_by("resolution")
                        ext = "mp4"
                        
                    target = s.desc().first() if quality == "Alta" else s.first()
                    
                    # Iniciar descarga (esto activará el callback y llenará la barra individual)
                    filename = f"{clean_filename(title)}.{ext}"
                    target.download(filename=filename)
                    
                    # Limpiar la barra individual al terminar y mostrar éxito
                    progress_bar.empty()
                    st.success(f"Completado: {filename}")
                    
            except Exception as e:
                st.error(f"Fallo al descargar {url}: {e}")
            
            # Actualizar progreso general
            current_progress = int(((index + 1) / total_videos) * 100)
            general_progress.progress(current_progress, text=f"Progreso General: {index + 1} / {total_videos}")
        
        # Finalización
        st.session_state.downloading = False
        st.balloons()
        st.success("¡Toda la cola ha sido procesada!")
        
        # Opcional: limpiar la cola automáticamente al terminar
        # st.session_state.video_queue = [] 
else:
    st.info("Añade enlaces arriba para comenzar.")

# --- Vista previa de la cola en pequeño ---
if st.session_state.video_queue and not st.session_state.downloading:
    with st.expander("Ver videos en cola", expanded=True):
        for u in st.session_state.video_queue:
            st.caption(f"🔗 {u}")