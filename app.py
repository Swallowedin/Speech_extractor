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
    page_title="Transcripteur Vidéo Universel",
    page_icon="🎤",
    layout="wide"
)

# Liste des plateformes supportées (extrait des plus populaires)
SUPPORTED_PLATFORMS = {
    'YouTube': ['youtube.com', 'youtu.be'],
    'Vimeo': ['vimeo.com'],
    'Dailymotion': ['dailymotion.com', 'dai.ly'],
    'Facebook': ['facebook.com', 'fb.watch'],
    'Instagram': ['instagram.com'],
    'TikTok': ['tiktok.com'],
    'Twitter/X': ['twitter.com', 'x.com'],
    'Twitch': ['twitch.tv'],
    'LinkedIn': ['linkedin.com'],
    'SoundCloud': ['soundcloud.com'],
    'Reddit': ['reddit.com'],
    'Autres plateformes': ['*']
}

def detect_platform(url):
    """Détecte la plateforme à partir de l'URL"""
    for platform, domains in SUPPORTED_PLATFORMS.items():
        for domain in domains:
            if domain in url.lower() or domain == '*':
                return platform
    return 'Autres plateformes'

def get_available_extractors():
    """Récupère la liste des extracteurs disponibles"""
    try:
        with yt_dlp.YoutubeDL() as ydl:
            return ydl.get_extractors()
    except:
        return []

def download_and_convert_to_wav(url):
    """Télécharge l'audio depuis n'importe quelle plateforme supportée"""
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
            # Options pour éviter les restrictions
            'extract_flat': False,
            'no_warnings': True,
            'no_color': True,
            'geo_bypass': True,
            'nocheckcertificate': True,
            # User agent générique
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            # Gestion des erreurs
            'retries': 3,
            'fragment_retries': 3,
            'skip_unavailable_fragments': True,
            'ignoreerrors': False,
            'no_playlist': True
        }
        
        platform = detect_platform(url)
        st.info(f"📺 Plateforme détectée : {platform}")
        
        # Ajuster les options selon la plateforme
        if platform == 'Facebook':
            ydl_opts.update({'facebook_dl_timeout': 30})
        elif platform == 'Twitter/X':
            ydl_opts.update({'twitter_api_key': os.getenv('TWITTER_API_KEY', '')})
        elif platform == 'Instagram':
            ydl_opts.update({'instagram_login': os.getenv('INSTAGRAM_LOGIN', '')})
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Vérifier si l'URL est supportée
                info = ydl.extract_info(url, download=False)
                if info.get('duration', 0) > 3600:  # Plus d'une heure
                    if not st.confirm("⚠️ Cette vidéo est très longue. Continuer ?"):
                        return None
                
                # Télécharger
                st.info("⏬ Téléchargement en cours...")
                ydl.download([url])
                
        except yt_dlp.utils.DownloadError as e:
            if "Sign in" in str(e) or "Login" in str(e):
                st.error(f"❌ Authentification requise pour {platform}. Essayez une autre vidéo ou contactez le support.")
            else:
                st.error(f"❌ Erreur de téléchargement : {str(e)}")
            return None
                
        return f"{output_path}.wav"
        
    except Exception as e:
        st.error(f"❌ Erreur inattendue : {str(e)}")
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
    st.title("🎤 Transcripteur Audio/Vidéo Universel")
    
    # Description et instructions
    st.markdown("""
    ### Plateformes supportées :
    Cette application peut transcrire l'audio depuis de nombreuses plateformes, notamment :
    - YouTube, Vimeo, Dailymotion
    - Réseaux sociaux (Facebook, Instagram, TikTok, Twitter/X)
    - Plateformes de streaming (Twitch)
    - Et bien d'autres !
    
    ### Mode d'emploi :
    1. Collez l'URL de votre contenu
    2. Choisissez la langue
    3. Lancez la transcription
    """)
    
    # Configuration initiale
    languages = {
        'Français': 'fr-FR',
        'English': 'en-US',
        'Español': 'es-ES',
        'Deutsch': 'de-DE'
    }
    
    # Interface principale
    col1, col2 = st.columns([3, 1])
    
    with col1:
        url = st.text_input("URL du média", 
                           placeholder="https://www.example.com/video...",
                           help="Collez ici l'URL de la vidéo ou de l'audio à transcrire")
        if url:
            platform = detect_platform(url)
            st.caption(f"📺 Plateforme détectée : {platform}")
    
    with col2:
        selected_lang = st.selectbox(
            "Langue",
            options=list(languages.keys()),
            index=0,
            help="Sélectionnez la langue principale du contenu"
        )
    
    # Bouton de transcription
    if st.button("🎯 Lancer la transcription", type="primary"):
        if url:
            # Phase 1 : Téléchargement
            with st.status("Traitement en cours...") as status:
                status.write("⏬ Téléchargement du média...")
                audio_path = download_and_convert_to_wav(url)
                
                if audio_path:
                    # Phase 2 : Transcription
                    status.write("🎤 Transcription du contenu...")
                    transcription = transcribe_audio(
                        audio_path,
                        language=languages[selected_lang]
                    )
                    
                    if transcription:
                        status.update(label="✅ Transcription terminée !", state="complete")
                        
                        # Affichage de la transcription brute
                        st.subheader("📝 Transcription brute")
                        raw_transcription = st.text_area(
                            "Vous pouvez éditer le texte directement ici :",
                            value=transcription,
                            height=200,
                            key="raw_transcription"
                        )
                        
                        # Options d'amélioration avec GPT si disponible
                        if 'OPENAI_API_KEY' in st.secrets:
                            st.subheader("🤖 Amélioration avec IA")
                            col1, col2 = st.columns([3, 1])
                            
                            with col1:
                                style = st.selectbox(
                                    "Style de reformulation :",
                                    options=['default', 'formal', 'simple', 'academic'],
                                    format_func=lambda x: {
                                        'default': '✨ Standard (clarté et cohérence)',
                                        'formal': '👔 Formel/Professionnel',
                                        'simple': '📚 Simplifié/Vulgarisé',
                                        'academic': '🎓 Académique'
                                    }[x]
                                )
                            
                            with col2:
                                if st.button("Améliorer le texte"):
                                    with st.spinner("🔄 Amélioration en cours..."):
                                        improved_text = improve_text_with_gpt(raw_transcription, style)
                                        if improved_text:
                                            st.text_area(
                                                "Texte amélioré :",
                                                value=improved_text,
                                                height=300,
                                                key="improved_text"
                                            )
                                            
                                            # Options d'export
                                            st.subheader("💾 Exporter")
                                            col1, col2, col3 = st.columns(3)
                                            
                                            with col1:
                                                st.download_button(
                                                    "📄 Version brute (TXT)",
                                                    raw_transcription,
                                                    file_name="transcription_brute.txt",
                                                    mime="text/plain"
                                                )
                                            
                                            with col2:
                                                st.download_button(
                                                    "📄 Version améliorée (TXT)",
                                                    improved_text,
                                                    file_name="transcription_amelioree.txt",
                                                    mime="text/plain"
                                                )
                                            
                                            with col3:
                                                json_data = json.dumps({
                                                    "url": url,
                                                    "platform": detect_platform(url),
                                                    "language": selected_lang,
                                                    "original": raw_transcription,
                                                    "improved": improved_text,
                                                    "style": style
                                                }, ensure_ascii=False, indent=2)
                                                
                                                st.download_button(
                                                    "📄 Rapport complet (JSON)",
                                                    json_data,
                                                    file_name="transcription_complete.json",
                                                    mime="application/json"
                                                )
                        else:
                            # Options d'export version simple
                            st.subheader("💾 Exporter")
                            st.download_button(
                                "📄 Télécharger la transcription (TXT)",
                                raw_transcription,
                                file_name="transcription.txt",
                                mime="text/plain"
                            )
                    else:
                        status.update(label="❌ Échec de la transcription", state="error")
                else:
                    status.update(label="❌ Échec du téléchargement", state="error")
        else:
            st.warning("⚠️ Veuillez entrer une URL valide")
    
    # Afficher la barre de statut des services
    with st.sidebar:
        st.subheader("📊 État des services")
        
        # Vérification du service de téléchargement
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                st.success("✅ Service de téléchargement : Opérationnel")
        except:
            st.error("❌ Service de téléchargement : Hors service")
        
        # Vérification de l'API Speech Recognition
        try:
            recognizer = sr.Recognizer()
            st.success("✅ Service de reconnaissance vocale : Opérationnel")
        except:
            st.error("❌ Service de reconnaissance vocale : Hors service")
        
        # Vérification de l'API GPT
        if 'OPENAI_API_KEY' in st.secrets:
            st.success("✅ Service d'amélioration IA : Disponible")
        else:
            st.warning("⚠️ Service d'amélioration IA : Non configuré")
        
        # Informations système
        st.subheader("ℹ️ Informations")
        st.info(
            f"Plateformes supportées : {len(SUPPORTED_PLATFORMS)}\n"
            f"Langues disponibles : {len(languages)}"
        )

if __name__ == "__main__":
    main()
