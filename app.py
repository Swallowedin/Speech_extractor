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

# Configuration de l'API OpenAI
if 'OPENAI_API_KEY' not in st.secrets:
    st.sidebar.warning('⚠️ Ajoutez votre clé API OpenAI dans les secrets')

def process_with_gpt(text, style='default'):
    """Traite le texte avec GPT pour l'améliorer"""
    client = OpenAI(api_key=st.secrets['OPENAI_API_KEY'])
    
    style_prompts = {
        'default': "Reformule ce texte pour le rendre plus clair et cohérent, en corrigeant les erreurs éventuelles tout en gardant le sens original :",
        'formal': "Reformule ce texte dans un style formel et professionnel, adapté pour un contexte d'entreprise :",
        'simple': "Reformule ce texte pour le rendre plus simple et facile à comprendre, comme si tu l'expliquais à quelqu'un :",
        'academic': "Reformule ce texte dans un style académique, avec un vocabulaire précis et une structure claire :"
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
        st.error(f"Erreur lors du traitement GPT: {str(e)}")
        return None

# [Le reste des fonctions précédentes reste identique jusqu'à main()]

def main():
    st.title("🎤 Transcripteur Vidéo avec Amélioration IA")
    
    st.markdown("""
    ### Comment utiliser:
    1. Collez l'URL d'une vidéo YouTube
    2. Choisissez la langue de la vidéo
    3. Cliquez sur 'Transcrire'
    4. Utilisez l'IA pour améliorer la transcription
    
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
            if duration and duration > 600:
                st.warning("⚠️ Cette vidéo est longue et pourrait prendre beaucoup de temps à traiter.")
            
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
                    
                    # Afficher la transcription brute
                    st.text_area(
                        "Transcription brute:",
                        value=transcription,
                        height=200,
                        key="raw_transcription"
                    )
                    
                    # Options d'amélioration avec GPT
                    st.subheader("Amélioration avec IA")
                    style = st.selectbox(
                        "Choisissez un style de reformulation:",
                        options=['default', 'formal', 'simple', 'academic'],
                        format_func=lambda x: {
                            'default': 'Standard (clarté et cohérence)',
                            'formal': 'Formel/Professionnel',
                            'simple': 'Simplifié/Vulgarisé',
                            'academic': 'Académique'
                        }[x]
                    )
                    
                    if st.button("Améliorer avec GPT"):
                        with st.spinner("Amélioration du texte en cours..."):
                            improved_text = process_with_gpt(transcription, style)
                            if improved_text:
                                st.text_area(
                                    "Texte amélioré:",
                                    value=improved_text,
                                    height=300,
                                    key="improved_text"
                                )
                                
                                # Boutons d'export
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.download_button(
                                        "📄 Télécharger en TXT",
                                        improved_text,
                                        file_name="transcription_amelioree.txt",
                                        mime="text/plain"
                                    )
                                
                                with col2:
                                    json_data = json.dumps(
                                        {
                                            "transcription_originale": transcription,
                                            "transcription_amelioree": improved_text,
                                            "style_utilise": style
                                        },
                                        ensure_ascii=False,
                                        indent=2
                                    )
                                    st.download_button(
                                        "📄 Télécharger en JSON",
                                        json_data,
                                        file_name="transcription_complete.json",
                                        mime="application/json"
                                    )
        else:
            st.warning("⚠️ Veuillez entrer une URL valide")

if __name__ == "__main__":
    main()
