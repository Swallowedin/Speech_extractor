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

# Initialisation de l'API OpenAI si la clé est présente
if 'OPENAI_API_KEY' in st.secrets:
    client = OpenAI(api_key=st.secrets['OPENAI_API_KEY'])
else:
    st.sidebar.warning('⚠️ Ajoutez votre clé API OpenAI dans les secrets')

def download_and_convert_to_wav(url):
    """Télécharge la vidéo et la convertit en WAV"""
    try:
        # Créer un dossier temporaire
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, 'audio')
        
        # Configuration de yt-dlp
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
        
        # Téléchargement
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        return f"{output_path}.wav"
    except Exception as e:
        st.error(f"Erreur lors du téléchargement: {str(e)}")
        return None

def transcribe_audio(audio_path, language='fr-FR'):
    """Transcrit le fichier audio"""
    recognizer = sr.Recognizer()
    full_text = []
    
    try:
        with sr.AudioFile(audio_path) as source:
            # Ajuster pour le bruit ambiant
            recognizer.adjust_for_ambient_noise(source)
            
            # Lire l'audio
            audio = recognizer.record(source)
            
            # Transcrire
            text = recognizer.recognize_google(audio, language=language)
            full_text.append(text)
            
        return ' '.join(full_text)
    except sr.UnknownValueError:
        st.error("La parole n'a pas pu être reconnue")
        return None
    except sr.RequestError as e:
        st.error(f"Erreur avec le service de reconnaissance: {e}")
        return None
    except Exception as e:
        st.error(f"Erreur inattendue: {e}")
        return None
    finally:
        # Nettoyage
        if os.path.exists(audio_path):
            os.remove(audio_path)

def improve_text_with_gpt(text, style='default'):
    """Améliore le texte avec GPT"""
    if 'OPENAI_API_KEY' not in st.secrets:
        st.error("Clé API OpenAI manquante")
        return None
        
    style_prompts = {
        'default': "Reformule ce texte pour le rendre plus clair et cohérent :",
        'formal': "Reformule ce texte dans un style formel et professionnel :",
        'simple': "Reformule ce texte pour le rendre plus simple à comprendre :",
        'academic': "Reformule ce texte dans un style académique :"
    }
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
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
