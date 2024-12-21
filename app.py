import streamlit as st
import yt_dlp
import os
import speech_recognition as sr
import tempfile
import subprocess
import json

st.set_page_config(
    page_title="Transcripteur Vidéo", 
    page_icon="🎤",
    layout="wide"
)

def check_video_length(url):
    """Vérifie la durée de la vidéo"""
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'force_generic_extractor': True
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=False)
            duration = result.get('duration', 0)
            return duration
    except Exception:
        return None

def download_audio(url):
    """Télécharge l'audio d'une vidéo"""
    temp_dir = tempfile.mkdtemp()
    output_path = os.path.join(temp_dir, 'audio')
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'outtmpl': output_path,
        'quiet': True
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return f"{output_path}.wav"
    except Exception as e:
        st.error(f"Erreur lors du téléchargement: {str(e)}")
        return None

def transcribe_audio(audio_path, language='fr-FR'):
    """Transcrit un fichier audio"""
    recognizer = sr.Recognizer()
    transcription = []
    
    try:
        # Diviser l'audio en segments de 30 secondes
        segment_duration = 30  # en secondes
        segment_dir = tempfile.mkdtemp()
        
        # Utiliser ffmpeg pour diviser l'audio
        command = [
            'ffmpeg', '-i', audio_path,
            '-f', 'segment',
            '-segment_time', str(segment_duration),
            '-c', 'copy',
            os.path.join(segment_dir, 'segment_%03d.wav')
        ]
        
        subprocess.run(command, capture_output=True)
        
        # Transcrire chaque segment
        segments = sorted([f for f in os.listdir(segment_dir) if f.startswith('segment_')])
        progress_bar = st.progress(0)
        
        for i, segment_file in enumerate(segments):
            segment_path = os.path.join(segment_dir, segment_file)
            
            with sr.AudioFile(segment_path) as source:
                audio = recognizer.record(source)
                try:
                    text = recognizer.recognize_google(audio, language=language)
                    transcription.append(text)
                except sr.UnknownValueError:
                    st.warning(f"Segment {i+1} inaudible")
                except sr.RequestError as e:
                    st.error(f"Erreur API: {str(e)}")
            
            progress_bar.progress((i + 1) / len(segments))
            os.remove(segment_path)
        
        return ' '.join(transcription)
        
    except Exception as e:
        st.error(f"Erreur de transcription: {str(e)}")
        return None
        
    finally:
        # Nettoyage
        if os.path.exists(audio_path):
            os.remove(audio_path)
        if os.path.exists(segment_dir):
            for file in os.listdir(segment_dir):
                try:
                    os.remove(os.path.join(segment_dir, file))
                except:
                    pass
            os.rmdir(segment_dir)

def main():
    st.title("🎤 Transcripteur Vidéo en Texte")
    
    st.markdown("""
    ### Comment utiliser:
    1. Collez l'URL d'une vidéo YouTube
    2. Choisissez la langue de la vidéo
    3. Cliquez sur 'Transcrire'
    
    ⚠️ Pour de meilleurs résultats, utilisez des vidéos de moins de 10 minutes.
    """)
    
    # Sélection de la langue
    languages = {
        'Français': 'fr-FR',
        'English': 'en-US',
        'Español': 'es-ES',
        'Deutsch': 'de-DE'
    }
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        url = st.text_input(
            "URL YouTube",
            placeholder="https://www.youtube.com/watch?v=..."
        )
    
    with col2:
        selected_lang = st.selectbox(
            "Langue",
            options=list(languages.keys()),
            index=0
        )
    
    if st.button("Transcrire", type="primary"):
        if url:
            # Vérifier la durée de la vidéo
            duration = check_video_length(url)
            if duration and duration > 600:  # 10 minutes
                st.warning("⚠️ Cette vidéo est longue et pourrait prendre beaucoup de temps à traiter. Considérez utiliser une vidéo plus courte.")
            
            with st.spinner("Téléchargement de l'audio..."):
                audio_path = download_audio(url)
                
            if audio_path:
                with st.spinner("Transcription en cours..."):
                    transcription = transcribe_audio(
                        audio_path,
                        language=languages[selected_lang]
                    )
                    
                if transcription:
                    st.success("✅ Transcription terminée!")
                    
                    # Afficher la transcription dans une zone de texte éditable
                    edited_transcription = st.text_area(
                        "Transcription (éditable):",
                        value=transcription,
                        height=300
                    )
                    
                    # Boutons de téléchargement
                    col1, col2 = st.columns(2)
                    with col1:
                        st.download_button(
                            "📄 Télécharger en TXT",
                            edited_transcription,
                            file_name="transcription.txt",
                            mime="text/plain"
                        )
                    
                    with col2:
                        json_data = json.dumps(
                            {"transcription": edited_transcription},
                            ensure_ascii=False,
                            indent=2
                        )
                        st.download_button(
                            "📄 Télécharger en JSON",
                            json_data,
                            file_name="transcription.json",
                            mime="application/json"
                        )
        else:
            st.warning("⚠️ Veuillez entrer une URL valide")

if __name__ == "__main__":
    main()
