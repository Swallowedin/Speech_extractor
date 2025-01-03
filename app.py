import streamlit as st
import yt_dlp
import os
import speech_recognition as sr
import tempfile
import subprocess
import json
from pydub import AudioSegment

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
if 'file_source' not in st.session_state:
    st.session_state.file_source = None

def process_uploaded_file(uploaded_file):
    """Traite le fichier uploadé et le convertit en WAV"""
    try:
        temp_dir = tempfile.mkdtemp()
        
        # Sauvegarder le fichier uploadé
        input_path = os.path.join(temp_dir, uploaded_file.name)
        with open(input_path, 'wb') as f:
            f.write(uploaded_file.getbuffer())
            
        # Créer le chemin de sortie pour le fichier WAV
        output_path = os.path.join(temp_dir, 'audio.wav')
        
        # Convertir en WAV avec ffmpeg
        command = [
            'ffmpeg', '-i', input_path,
            '-acodec', 'pcm_s16le',
            '-ar', '44100',
            '-ac', '2',
            output_path
        ]
        
        subprocess.run(command, capture_output=True)
        
        # Vérifier si le fichier existe
        if not os.path.exists(output_path):
            st.error("❌ Erreur lors de la conversion du fichier audio")
            return None
            
        return output_path
        
    except Exception as e:
        st.error(f"❌ Erreur lors du traitement du fichier : {str(e)}")
        return None

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

def is_peertube_instance(url):
    """Détecte si l'URL provient d'une instance PeerTube"""
    try:
        import requests
        from urllib.parse import urlparse

        # Parse l'URL pour obtenir le domaine et le chemin
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Vérifie si l'API PeerTube est disponible sur ce domaine
        try:
            response = requests.get(f"{base_url}/api/v1/config", timeout=5)
            if response.ok and 'instance' in response.json():
                return True
        except:
            # Essaie une autre approche si la première échoue
            try:
                response = requests.get(f"{base_url}/api/v1/videos", timeout=5)
                return response.ok and 'data' in response.json()
            except:
                pass
        return False
    except:
        return False

def extract_peertube_video_id(url):
    """Extrait l'ID de la vidéo PeerTube depuis l'URL"""
    from urllib.parse import urlparse, parse_qs
    
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.split('/')
    
    # Cherche d'abord un ID après /w/ (format courant de PeerTube)
    for i, part in enumerate(path_parts):
        if part == 'w' and i + 1 < len(path_parts):
            # L'ID est la partie après 'w'
            video_id = path_parts[i + 1].split('?')[0]  # Enlève les paramètres d'URL
            return video_id
    
    # Si pas trouvé avec /w/, essaie d'autres formats courants
    for part in path_parts:
        # Ignore les parties vides ou communes
        if not part or part in ['watch', 'videos', 'v', 'w']:
            continue
        # Vérifie si la partie ressemble à un ID PeerTube (longueur > 8 et alphanumérique)
        if len(part) > 8 and part.replace('-', '').isalnum():
            return part
    
    # En dernier recours, cherche dans les paramètres d'URL
    params = parse_qs(parsed_url.query)
    for param in ['v', 'video', 'videoId']:
        if param in params:
            return params[param][0]
    
    return None

def download_from_peertube(url, output_path):
    """Télécharge une vidéo depuis n'importe quelle instance PeerTube"""
    try:
        import requests
        from urllib.parse import urlparse

        # Parse l'URL pour obtenir le domaine
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Extrait l'ID de la vidéo
        video_id = extract_peertube_video_id(url)
        if not video_id:
            raise ValueError("Impossible d'extraire l'ID de la vidéo")

        # Récupère les informations de la vidéo via l'API
        api_url = f"{base_url}/api/v1/videos/{video_id}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        response = requests.get(api_url, headers=headers)
        if not response.ok:
            raise Exception(f"Erreur API: {response.status_code}")
        
        video_data = response.json()
        
        # Cherche la meilleure qualité audio disponible
        best_audio = None
        if 'files' in video_data:
            # Trie par résolution décroissante pour avoir la meilleure qualité
            files = sorted(video_data['files'], key=lambda x: x.get('resolution', {}).get('id', 0), reverse=True)
            if files:
                best_audio = files[0]
        
        if not best_audio:
            raise Exception("Aucun fichier audio trouvé")
        
        # Télécharge le fichier
        direct_url = best_audio['fileUrl']
        if not direct_url.startswith('http'):
            direct_url = f"{base_url}{direct_url}"
            
        temp_file = f"{output_path}_temp.mp4"
        with requests.get(direct_url, stream=True, headers=headers) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            
            with open(temp_file, 'wb') as f:
                if total_size == 0:
                    f.write(r.content)
                else:
                    dl = 0
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            dl += len(chunk)
                            f.write(chunk)
                            done = int(50 * dl / total_size)
                            if done % 5 == 0:
                                st.write(f"Téléchargement: [{'=' * done}{' ' * (50-done)}] {dl*100/total_size:.1f}%")
        
        # Convertit en WAV
        subprocess.run([
            'ffmpeg', '-i', temp_file,
            '-vn', '-acodec', 'pcm_s16le',
            '-ar', '44100', '-ac', '2',
            f"{output_path}.wav"
        ], capture_output=True)
        
        # Nettoie le fichier temporaire
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        return f"{output_path}.wav"
        
    except Exception as e:
        st.error(f"❌ Erreur lors du téléchargement PeerTube : {str(e)}")
        return None

# Modification de la fonction download_and_convert_to_wav
def download_and_convert_to_wav(url):
    """Télécharge l'audio depuis n'importe quelle plateforme supportée"""
    try:
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, 'audio')
        
        # Vérifie d'abord si c'est une instance PeerTube
        if is_peertube_instance(url):
            st.info("📺 Instance PeerTube détectée")
            return download_from_peertube(url, output_path)
        
        # Si ce n'est pas PeerTube, utilise la configuration standard yt-dlp
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
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get('duration', 0) > 3600:  # Plus d'une heure
                if not st.confirm("⚠️ Cette vidéo est très longue. Continuer ?"):
                    return None
            
            st.info("⏬ Téléchargement en cours...")
            ydl.download([url])
            
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
    try:
        import openai  # Import local
        
        if 'OPENAI_API_KEY' not in st.secrets:
            st.warning("⚠️ Clé API OpenAI non configurée.")
            return None
            
        openai.api_key = st.secrets['OPENAI_API_KEY']
        
        style_prompts = {
            'default': "Reformule ce texte pour le rendre plus clair et cohérent :",
            'formal': "Reformule ce texte dans un style formel et professionnel :",
            'simple': "Reformule ce texte pour le rendre plus simple à comprendre :",
            'academic': "Reformule ce texte dans un style académique :"
        }
        
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Tu es un expert en réécriture et amélioration de texte."},
                {"role": "user", "content": f"{style_prompts[style]}\n\n{text}"}
            ],
            temperature=0.7
        )
        
        return response.choices[0].message.content
        
    except ImportError:
        st.error("❌ Module OpenAI non installé")
        return None
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
    1. Choisissez votre source (URL ou fichier local)
    2. Sélectionnez la langue
    3. Lancez la transcription
    4. Utilisez l'IA pour améliorer le texte si besoin
    """)
    
    languages = {
        'Français': 'fr-FR',
        'English': 'en-US',
        'Español': 'es-ES',
        'Deutsch': 'de-DE'
    }
    
    # Onglets pour choisir la source
    source_tab1, source_tab2 = st.tabs(["🌐 URL", "📁 Fichier local"])
    
    with source_tab1:
        url = st.text_input("URL du média", 
                           placeholder="https://www.example.com/video...")
        if url:
            platform = detect_platform(url)
            st.caption(f"📺 Plateforme détectée : {platform}")
            st.session_state.file_source = None
            st.session_state.url = url
    
    with source_tab2:
        uploaded_file = st.file_uploader(
            "Choisissez un fichier audio/vidéo",
            type=['mp3', 'mp4', 'wav', 'm4a', 'ogg'],
            help="Formats supportés : MP3, MP4, WAV, M4A, OGG"
        )
        if uploaded_file:
            st.caption(f"📁 Fichier sélectionné : {uploaded_file.name}")
            st.session_state.url = None
            st.session_state.file_source = uploaded_file
    
    # Sélection de la langue
    selected_lang = st.selectbox("Langue", options=list(languages.keys()), index=0)
    
    # Bouton de transcription
    if st.button("🎯 Lancer la transcription", type="primary"):
        if not st.session_state.url and not st.session_state.file_source:
            st.warning("⚠️ Veuillez d'abord choisir une source (URL ou fichier)")
            return
            
        audio_path = None
        
        with st.status("Traitement en cours...") as status:
            if st.session_state.url:
                status.write("⏬ Téléchargement du média...")
                audio_path = download_and_convert_to_wav(st.session_state.url)
            elif st.session_state.file_source:
                status.write("📝 Traitement du fichier local...")
                audio_path = process_uploaded_file(st.session_state.file_source)
            
            if audio_path:
                status.write("🎤 Transcription du contenu...")
                transcription = transcribe_audio(
                    audio_path,
                    language=languages[selected_lang]
                )
                
                if transcription:
                    status.update(label="✅ Transcription terminée !", state="complete")
                    st.session_state.transcription = transcription
    
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
                                # Sauvegarder le rapport complet
                                source_info = {
                                    "type": "url" if st.session_state.url else "file",
                                    "source": st.session_state.url if st.session_state.url else st.session_state.file_source.name
                                }
                                
                                json_data = json.dumps({
                                    "source": source_info,
                                    "platform": detect_platform(st.session_state.url) if st.session_state.url else "local_file",
                                    "language": selected_lang,
                                    "original": raw_transcription,
                                    "improved": improved_text,
                                    "style": style,
                                    "timestamp": datetime.datetime.now().isoformat()
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
        if st.button("🗑️ Effacer les résultats", type="secondary"):
            st.session_state.transcription = None
            st.session_state.url = None
            st.session_state.file_source = None
            st.session_state.improved_text = None
            st.experimental_rerun()

if __name__ == "__main__":
    main()
