import streamlit as st
import yt_dlp
import os
import speech_recognition as sr
import tempfile
import subprocess
import json
from openai import OpenAI

# Configuration de la page
st.set_page_config(
    page_title="Transcripteur Vidéo",
    page_icon="🎤",
    layout="wide"
)

def get_openai_client():
    """Initialise le client OpenAI uniquement si nécessaire"""
    if 'OPENAI_API_KEY' in st.secrets:
        return OpenAI(api_key=st.secrets['OPENAI_API_KEY'])
    st.sidebar.warning('⚠️ Ajoutez votre clé API OpenAI dans les secrets')
    return None

def download_and_convert_to_wav(url):
    """Télécharge la vidéo et la convertit en WAV avec des options avancées"""
    try:
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, 'audio')
        
        # Configuration avancée de yt-dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
            'outtmpl': output_path,
            'quiet': True,
            # Options pour éviter les limites de YouTube
            'cookiesfrombrowser': ('chrome',),  # Utilise les cookies de Chrome
            'extract_flat': False,
            'no_warnings': True,
            'no_color': True,
            'geo_bypass': True,
            'nocheckcertificate': True,
            # User agent aléatoire
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            # Ajout de retries
            'retries': 3,
            'fragment_retries': 3,
            'skip_download': False,
            'hls_prefer_native': True
        }
        
        # Essayer de télécharger avec différentes options si nécessaire
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            if "Sign in to confirm you're not a bot" in str(e):
                st.warning("⚠️ YouTube demande une vérification. Tentative avec des options alternatives...")
                # Essayer avec des options différentes
                ydl_opts.update({
                    'format': 'worstaudio/worst',  # Qualité inférieure mais plus facile à télécharger
                })
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            else:
                raise e
                
        return f"{output_path}.wav"
    except Exception as e:
        st.error(f"Erreur lors du téléchargement: {str(e)}\n\nEssayez de :\n1. Utiliser une autre vidéo\n2. Vérifier que la vidéo est publique\n3. Attendre quelques minutes et réessayer")
        return None

def transcribe_audio(audio_path, language='fr-FR'):
    """Transcrit le fichier audio en le découpant en segments"""
    recognizer = sr.Recognizer()
    transcription = []
    
    try:
        # Créer un dossier temporaire pour les segments
        segment_dir = tempfile.mkdtemp()
        segment_duration = 30  # en secondes
        
        # Utiliser ffmpeg pour diviser l'audio
        command = [
            'ffmpeg', '-i', audio_path,
            '-f', 'segment',
            '-segment_time', str(segment_duration),
            '-c', 'copy',
            os.path.join(segment_dir, 'segment_%03d.wav')
        ]
        
        subprocess.run(command, capture_output=True)
        
        # Traiter chaque segment
        segments = sorted([f for f in os.listdir(segment_dir) if f.startswith('segment_')])
        
        # Créer une barre de progression
        progress_text = "Transcription en cours..."
        progress_bar = st.progress(0, text=progress_text)
        
        for i, segment_file in enumerate(segments):
            segment_path = os.path.join(segment_dir, segment_file)
            
            with sr.AudioFile(segment_path) as source:
                audio = recognizer.record(source)
                try:
                    text = recognizer.recognize_google(audio, language=language)
                    transcription.append(text)
                except sr.UnknownValueError:
                    st.warning(f"⚠️ Segment {i+1} inaudible")
                    continue
                except sr.RequestError as e:
                    st.error(f"❌ Erreur API: {str(e)}")
                    continue
            
            # Mettre à jour la progression
            progress = (i + 1) / len(segments)
            progress_bar.progress(progress, text=f"{progress_text} ({int(progress * 100)}%)")
            
            # Nettoyer le segment
            os.remove(segment_path)
        
        progress_bar.progress(1.0, text="Transcription terminée !")
        return ' '.join(transcription)
        
    except Exception as e:
        st.error(f"Erreur de transcription: {str(e)}")
        return None
        
    finally:
        # Nettoyage des fichiers temporaires
        if os.path.exists(audio_path):
            os.remove(audio_path)
        if os.path.exists(segment_dir):
            for file in os.listdir(segment_dir):
                try:
                    os.remove(os.path.join(segment_dir, file))
                except:
                    pass
            os.rmdir(segment_dir)

def improve_text_with_gpt(text, style='default'):
    """Améliore le texte avec GPT"""
    client = get_openai_client()
    if not client:
        return None
        
    style_prompts = {
        'default': "Reformule ce texte pour le rendre plus clair et cohérent :",
        'formal': "Reformule ce texte dans un style formel et professionnel :",
        'simple': "Reformule ce texte pour le rendre plus simple à comprendre :",
        'academic': "Reformule ce texte dans un style académique :"
    }
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Tu es un expert en réécriture et amélioration de texte."},
                {"role": "user", "content": f"{style_prompts[style]}\n\n{text}"}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Erreur GPT: {str(e)}")
        return None

def main():
    st.title("🎤 Transcripteur Vidéo avec IA")
    
    st.markdown("""
    ### Mode d'emploi:
    1. Collez l'URL d'une vidéo YouTube
    2. Choisissez la langue
    3. Lancez la transcription
    4. Améliorez le texte avec l'IA
    """)
    
    # Interface utilisateur
    languages = {
        'Français': 'fr-FR',
        'English': 'en-US',
        'Español': 'es-ES',
        'Deutsch': 'de-DE'
    }
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        url = st.text_input("URL YouTube", placeholder="https://www.youtube.com/watch?v=...")
    
    with col2:
        selected_lang = st.selectbox("Langue", options=list(languages.keys()), index=0)
    
    if st.button("Transcrire", type="primary"):
        if url:
            with st.spinner("Traitement de la vidéo en cours..."):
                # Téléchargement et conversion
                audio_path = download_and_convert_to_wav(url)
                
                if audio_path:
                    # Transcription
                    transcription = transcribe_audio(audio_path, language=languages[selected_lang])
                    
                    if transcription:
                        st.success("✅ Transcription terminée!")
                        
                        # Affichage de la transcription
                        st.text_area(
                            "Transcription brute:",
                            value=transcription,
                            height=200,
                            key="raw_transcription"
                        )
                        
                        # Options d'amélioration
                        if 'OPENAI_API_KEY' in st.secrets:
                            st.subheader("Amélioration avec IA")
                            style = st.selectbox(
                                "Style de reformulation:",
                                options=['default', 'formal', 'simple', 'academic'],
                                format_func=lambda x: {
                                    'default': 'Standard',
                                    'formal': 'Formel',
                                    'simple': 'Simplifié',
                                    'academic': 'Académique'
                                }[x]
                            )
                            
                            if st.button("Améliorer avec GPT"):
                                with st.spinner("Amélioration du texte..."):
                                    improved_text = improve_text_with_gpt(transcription, style)
                                    if improved_text:
                                        st.text_area(
                                            "Texte amélioré:",
                                            value=improved_text,
                                            height=300,
                                            key="improved_text"
                                        )
                                        
                                        # Export
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.download_button(
                                                "📄 Télécharger TXT",
                                                improved_text,
                                                file_name="transcription_amelioree.txt",
                                                mime="text/plain"
                                            )
                                        
                                        with col2:
                                            json_data = json.dumps({
                                                "original": transcription,
                                                "improved": improved_text,
                                                "style": style
                                            }, ensure_ascii=False, indent=2)
                                            st.download_button(
                                                "📄 Télécharger JSON",
                                                json_data,
                                                file_name="transcription.json",
                                                mime="application/json"
                                            )
        else:
            st.warning("⚠️ Veuillez entrer une URL valide")

if __name__ == "__main__":
    main()
