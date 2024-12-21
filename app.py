import streamlit as st
import yt_dlp
import os
import speech_recognition as sr
from pydub import AudioSegment
import tempfile

st.set_page_config(page_title="Transcripteur Vidéo", page_icon="🎤")

def download_audio(url):
    """Télécharge l'audio d'une vidéo"""
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'outtmpl': 'temp_audio.%(ext)s'
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return 'temp_audio.wav'
    except Exception as e:
        st.error(f"Erreur lors du téléchargement: {str(e)}")
        return None

def transcribe_audio(audio_path):
    """Transcrit un fichier audio en texte"""
    recognizer = sr.Recognizer()
    
    try:
        # Charger l'audio
        audio = AudioSegment.from_wav(audio_path)
        
        # Découper en segments de 30 secondes pour une meilleure gestion
        segment_length = 30 * 1000  # 30 secondes en millisecondes
        segments = [audio[i:i+segment_length] for i in range(0, len(audio), segment_length)]
        
        transcription = []
        progress_bar = st.progress(0)
        
        for i, segment in enumerate(segments):
            # Sauvegarder le segment temporairement
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                segment.export(temp_file.name, format='wav')
                
                # Transcrire le segment
                with sr.AudioFile(temp_file.name) as source:
                    audio_data = recognizer.record(source)
                    try:
                        text = recognizer.recognize_google(audio_data, language='fr-FR')
                        transcription.append(text)
                    except sr.UnknownValueError:
                        st.warning(f"Impossible de transcrire le segment {i+1}")
                    except sr.RequestError as e:
                        st.error(f"Erreur API Google Speech Recognition: {str(e)}")
                
                # Mettre à jour la barre de progression
                progress = (i + 1) / len(segments)
                progress_bar.progress(progress)
                
            # Nettoyer le fichier temporaire
            os.unlink(temp_file.name)
        
        return ' '.join(transcription)
    
    except Exception as e:
        st.error(f"Erreur lors de la transcription: {str(e)}")
        return None
    finally:
        # Nettoyer le fichier audio principal
        if os.path.exists(audio_path):
            os.remove(audio_path)

def main():
    st.title("🎤 Transcripteur Vidéo en Texte")
    
    st.markdown("""
    Cette application permet de transcrire en texte l'audio d'une vidéo YouTube.
    Il suffit de coller l'URL de la vidéo ci-dessous.
    """)
    
    # Interface utilisateur
    url = st.text_input("URL de la vidéo YouTube", 
                       placeholder="https://www.youtube.com/watch?v=...")
    
    if st.button("Transcrire", type="primary"):
        if url:
            with st.spinner("Téléchargement de l'audio..."):
                audio_path = download_audio(url)
                
            if audio_path:
                with st.spinner("Transcription en cours..."):
                    transcription = transcribe_audio(audio_path)
                    
                if transcription:
                    st.success("Transcription terminée!")
                    st.markdown("### Transcription:")
                    st.markdown(transcription)
                    
                    # Bouton pour télécharger la transcription
                    st.download_button(
                        label="Télécharger la transcription",
                        data=transcription,
                        file_name="transcription.txt",
                        mime="text/plain"
                    )
        else:
            st.warning("Veuillez entrer une URL valide")

if __name__ == "__main__":
    main()
