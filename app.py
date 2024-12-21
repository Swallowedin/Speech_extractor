# app.py
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

# Liste des plateformes supportées
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

# Initialisation du session_state
if 'transcription' not in st.session_state:
    st.session_state.transcription = None
if 'url' not in st.session_state:
    st.session_state.url = None

def get_openai_client():
    """Initialise le client OpenAI uniquement si nécessaire"""
    try:
        if 'OPENAI_API_KEY' in st.secrets:
            client = OpenAI(
                api_key=st.secrets['OPENAI_API_KEY'],
                base_url="https://api.openai.com/v1"  # URL API explicite
            )
            return client
    except Exception as e:
        st.warning('⚠️ Configuration OpenAI manquante ou invalide')
        st.error(f"Erreur : {str(e)}")
    return None

def detect_platform(url):
    """Détecte la plateforme à partir de l'URL"""
    for platform, domains in SUPPORTED_PLATFORMS.items():
        for domain in domains:
            if domain in url.lower() or domain == '*':
                return platform
    return 'Autres plateformes'

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
            'extract_flat': False,
            'no_warnings': True,
            'no_color': True,
            'geo_bypass': True,
            'nocheckcertificate': True,
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
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
                info = ydl.extract_info(url, download=False)
                if info.get('duration', 0) > 3600:  # Plus d'une heure
                    if not st.confirm("⚠️ Cette vidéo est très longue. Continuer ?"):
                        return None
                
                st.info("⏬ Téléchargement en cours...")
                ydl.download([url])
                
        except yt_dlp.utils.DownloadError as e:
            if "Sign in" in str(e) or "Login" in str(e):
                st.error(f"❌ Authentification requise pour {platform}")
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
    if 'OPENAI_API_KEY' not in st.secrets:
        st.warning("⚠️ Clé API OpenAI non configurée. L'amélioration du texte n'est pas disponible.")
        return None
        
    try:
        client = get_openai_client()
        if not client:
            return None
            
        style_prompts = {
            'default': "Reformule ce texte pour le rendre plus clair et cohérent :",
            'formal': "Reformule ce texte dans un style formel et professionnel :",
            'simple': "Reformule ce texte pour le rendre plus simple à comprendre :",
            'academic': "Reformule ce texte dans un style académique :"
        }
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Tu es un expert en réécriture et amélioration de texte."},
                {"role": "user", "content": f"{style_prompts[style]}\n\n{text}"}
            ],
            temperature=0.7
        )
        improved_text = response.choices[0].message.content
        st.session_state.improved_text = improved_text
        return improved_text
        
    except Exception as e:
        st.error(f"Erreur lors de l'amélioration du texte : {str(e)}")
        return None

def main():
    st.title("🎤 Transcripteur Audio/Vidéo Universel")
    
    # Sidebar pour la configuration YouTube
    with st.sidebar:
        st.header("Configuration YouTube")
        st.markdown("""
        Si vous rencontrez des erreurs d'authentification YouTube, ajoutez vos cookies ici :
        
        Pour obtenir vos cookies :
        1. Connectez-vous à YouTube
        2. Ouvrez les DevTools (F12)
        3. Allez dans l'onglet Application > Cookies
        4. Copiez les valeurs des cookies importants
        """)
        
        # Champs pour les cookies principaux
        if 'youtube_cookies' not in st.session_state:
            st.session_state.youtube_cookies = {}
            
        cookies = {
            'CONSENT': st.text_input('Cookie CONSENT', key='consent'),
            'VISITOR_INFO1_LIVE': st.text_input('Cookie VISITOR_INFO1_LIVE', key='visitor'),
            'LOGIN_INFO': st.text_input('Cookie LOGIN_INFO', key='login'),
            'SID': st.text_input('Cookie SID', key='sid'),
            'HSID': st.text_input('Cookie HSID', key='hsid'),
            'SSID': st.text_input('Cookie SSID', key='ssid'),
        }
        
        # Ne sauvegarder que les cookies non vides
        st.session_state.youtube_cookies = {k: v for k, v in cookies.items() if v}
        
        if st.button("Effacer les cookies"):
            st.session_state.youtube_cookies = {}
            st.experimental_rerun()
    
    st.markdown("""
    ### Mode d'emploi :
    1. Collez l'URL de votre contenu
    2. Choisissez la langue
    3. Lancez la transcription
    4. Utilisez l'IA pour améliorer le texte si besoin
    """)
    
    languages = {
        'Français': 'fr-FR',
        'English': 'en-US',
        'Español': 'es-ES',
        'Deutsch': 'de-DE'
    }
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        url = st.text_input("URL du média", 
                           placeholder="https://www.example.com/video...")
        if url:
            platform = detect_platform(url)
            st.caption(f"📺 Plateforme détectée : {platform}")
    
    with col2:
        selected_lang = st.selectbox("Langue", options=list(languages.keys()), index=0)
    
    # Bouton de transcription
    if st.button("🎯 Lancer la transcription", type="primary"):
        if url:
            with st.status("Traitement en cours...") as status:
                status.write("⏬ Téléchargement du média...")
                audio_path = download_and_convert_to_wav(url)
                
                if audio_path:
                    status.write("🎤 Transcription du contenu...")
                    transcription = transcribe_audio(
                        audio_path,
                        language=languages[selected_lang]
                    )
                    
                    if transcription:
                        status.update(label="✅ Transcription terminée !", state="complete")
                        st.session_state.transcription = transcription
                        st.session_state.url = url
    
    # Afficher la transcription et options d'amélioration
    if st.session_state.transcription:
        st.subheader("📝 Transcription")
        raw_transcription = st.text_area(
            "Vous pouvez éditer le texte directement ici :",
            value=st.session_state.transcription,
            height=200,
            key="raw_transcription"
        )
        
        # Vérifier si OpenAI est configuré
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
                            st.session_state.improved_text = improved_text
                            st.text_area(
                                "Texte amélioré :",
                                value=improved_text,
                                height=300,
                                key="improved_text"
                            )
                            
                            # Options d'export
                            st.subheader("💾 Exporter")
                            col1, col2 = st.columns(2)
                            
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
                                
                            # Sauvegarder le rapport complet
                            json_data = json.dumps({
                                "url": st.session_state.url,
                                "platform": detect_platform(st.session_state.url),
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
            st.info("💡 Pour améliorer le texte avec l'IA, configurez votre clé API OpenAI dans les secrets de l'application.")

    # Bouton pour effacer la transcription
    if st.session_state.transcription and st.sidebar.button("🗑️ Effacer les résultats"):
        st.session_state.transcription = None
        st.session_state.url = None
        st.session_state.improved_text = None
        st.experimental_rerun()

if __name__ == "__main__":
    main()
