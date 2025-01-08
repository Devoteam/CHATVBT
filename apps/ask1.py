import streamlit as st
from snowflake.snowpark.context import get_active_session
from snowflake.cortex import Complete
import snowflake.snowpark.functions as F
import pandas as pd
import time,json,logging, hashlib, base64
from datetime import datetime
from typing import Any, Dict, List, Optional



class Ask1App:
    def __init__(self, app_id=1):
        self.APP_ID = app_id
        self.setup_logging()
        self.load_app_config()


    def setup_logging(self):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    def load_app_config(self):
        session = get_active_session()
        query = f"""
            SELECT * 
            FROM VERTBAUDET.CHATBOT.CORTEX_APPS
            WHERE APP_ID={self.APP_ID}
        """
        results = session.sql(query).collect()
        row = results[0]
        self.APP_NAME = row['APP_NAME']  # Store the APP_NAME
        self.APP_TITLE = row['APP_NAME']  # Keep APP_TITLE for backwards compatibility
        self.DATABASE = row['APP_DATABASE']
        self.SCHEMA = row['APP_SCHEMA']
        self.STAGE = row['APP_STAGE']
        self.APP_LOGO_URL = row['APP_LOGO_URL']

    def log_to_snowflake(self, username, input_text, output_json, elapsed_time, resolution_time):
        session = get_active_session()
        session.sql(f"""
            INSERT INTO VERTBAUDET.CHATBOT.CORTEX_LOGS 
            (DateTime, Username, App_Name, App_ID, input_text, output_json, elapsed_time, resolution_time)
            VALUES (?, CURRENT_USER(), ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(), 
            self.APP_NAME,  # Use APP_NAME instead of APP_TITLE
            self.APP_ID,
            input_text, 
            json.dumps(output_json),
            elapsed_time,
            resolution_time
        )).collect()

    def calculate_resolution_time(self, elapsed_time):
        return elapsed_time * 0.7
    
    # @st.cache_data(ttl=3600)
    def fetch_key_questions(self):
        logging.info(f"fetch_key_questions called in {__class__.__name__}")
        session = get_active_session()
        user_bookmarks_query = f"""
            SELECT bk_question 
            FROM VERTBAUDET.CHATBOT.CORTEX_BOOKMARKS
            WHERE APP_ID = {self.APP_ID}
            AND BK_USERNAME = 'ALL'
            ORDER BY BK_UPDATED_AT DESC
            LIMIT 6
        """
        user_bookmarks = session.sql(user_bookmarks_query).collect()
        return [row['BK_QUESTION'] for row in user_bookmarks]
    
    # def display_key_questions(self):
    #     logging.info(f"display_key_questions called in {self.__class__.__name__}")
    #     st.markdown("<h2 style='text-align: center;'>Comment puis-je vous aider aujourd'hui ?</h2>", unsafe_allow_html=True)
        # key_questions = self.fetch_key_questions()
        # with st.container(border=True):
        #     col1, col2 = st.columns(2)
        #     for i, question in enumerate(key_questions):
        #         if i % 2 == 0:
        #             with col1:
        #                 if st.button(question, key=f"q_{i}_{hash(question)}"):
        #                     st.session_state.active_suggestion = question
        #         else:
        #             with col2:
        #                 if st.button(question, key=f"q_{i}_{hash(question)}"):
        #                     st.session_state.active_suggestion = question

    def load_and_display_image(self):
        session = get_active_session()
        try:
            with session.file.get_stream(self.APP_LOGO_URL) as file_stream:
                image_data = file_stream.read()
                col1, col2, col3 = st.columns([1,2,1])
                with col2:
                    st.image(image_data, width=500)
            return self.APP_LOGO_URL
        except Exception as e:
            st.error(f"Erreur lors du chargement de l'image : {e}")
            return None

    def insert_bookmark_data(self, question, lang):
        logging.info(f"Tentative d'ajout d'un Bookmark : app_id={self.APP_ID}, question={question}, lang={lang}")
        session = get_active_session()
        try:
            query = f"""
                INSERT INTO VERTBAUDET.CHATBOT.CORTEX_BOOKMARKS 
                (APP_ID, BK_USERNAME, BK_QUESTION, BK_LANG)
                VALUES (?, CURRENT_USER(), ?, ?)
            """
            result = session.sql(query, (self.APP_ID, question, lang)).collect()
            logging.info(f"Résultat de l'insertion du bookmark : {result}")
            return True
        except Exception as e:
            logging.error(f"Erreur lors de l'ajout du bookmark: {str(e)}")
            return False

    def add_bookmark_button(self, question, lang, message_index):
        logging.info(f"add_bookmark_button")
        question_hash = hashlib.md5(question.encode()).hexdigest()
        bookmark_button_key = f"add_bookmark_{message_index}_{question_hash}"
        
        bookmark_clicked = st.button("❤️", key=bookmark_button_key)
        
        if bookmark_clicked:
            logging.info(f"Button clicked")
            success = self.insert_bookmark_data(question, lang)
            if success:
                st.success("Question enregistrée dans vos favoris !")
                st.rerun() 
            else:
                st.error("Erreur lors de l'enregistrement du favori.")
        
    def display_user_bookmarks(self):
        st.markdown("""
            <style>
            .favorite-prompts {
                margin-top: 3rem;
                padding: 1rem;
                color: white;
                font-weight: bold;
            }
            </style>
        """, unsafe_allow_html=True)
        st.sidebar.markdown('<div class="favorite-prompts"> My Favorite Prompts ❤️</div>', unsafe_allow_html=True)
        bookmarks = self.fetch_user_bookmarks()
        if not bookmarks:
            st.sidebar.info("Vous n'avez pas encore de favoris.")
        else:
            for index, bookmark in enumerate(bookmarks):
                bookmark_container = st.sidebar.container()
                with bookmark_container:
                    col1, col2, col3 = st.columns([5, 1, 1])
                    with col1:
                        # Utilisation d'un div avec style pour contrôler l'affichage du texte
                        st.markdown(
                            f"""
                            <div style="
                                background-color: white;
                                border-radius: 4px;
                                padding: 8px;
                                margin-bottom: 4px;
                                color: black;
                                font-size: 14px;
                                white-space: normal;
                                word-wrap: break-word;
                            ">
                                {bookmark}
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    with col2:
                        if st.button("✏️", key=f"edit_bookmark_{index}_{hash(bookmark)}"):
                            st.session_state.editing_bookmark = bookmark
                            st.session_state.editing_bookmark_index = index
                    with col3:
                        if st.button("🗑️", key=f"delete_bookmark_{index}_{hash(bookmark)}"):
                            self.delete_bookmark(bookmark)
                            st.rerun()

        if 'editing_bookmark' in st.session_state:
            self.edit_bookmark_ui()


    def edit_bookmark_ui(self):
        st.markdown("""
            <style>
            .favorite-prompts {
                margin-top: 1rem;
                # padding: 1rem;
                color: white;
                font-weight: bold;
            }
            </style>
        """, unsafe_allow_html=True)
        st.sidebar.markdown('<div class="favorite-prompts">Modifier le favori</div>', unsafe_allow_html=True)
        new_bookmark = st.sidebar.text_input("Nouveau texte", value=st.session_state.editing_bookmark)
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.button("Enregistrer", key="save_edit_bookmark"):
                self.update_bookmark(st.session_state.editing_bookmark, new_bookmark)
                del st.session_state.editing_bookmark
                del st.session_state.editing_bookmark_index
                st.rerun()
        with col2:
            if st.button("Annuler", key="cancel_edit_bookmark"):
                del st.session_state.editing_bookmark
                del st.session_state.editing_bookmark_index
                st.rerun()

    def update_bookmark(self, old_bookmark, new_bookmark):
        session = get_active_session()
        update_query = f"""
            UPDATE VERTBAUDET.CHATBOT.CORTEX_BOOKMARKS
            SET BK_QUESTION = ?, BK_UPDATED_AT = CURRENT_TIMESTAMP()
            WHERE APP_ID = {self.APP_ID}
            AND BK_USERNAME = CURRENT_USER()
            AND BK_QUESTION = ?
        """
        session.sql(update_query, (new_bookmark, old_bookmark)).collect()
        logging.info(f"Favori mis à jour : '{old_bookmark}' -> '{new_bookmark}'")

    def delete_bookmark(self, question):
        session = get_active_session()
        delete_query = f"""
            DELETE FROM VERTBAUDET.CHATBOT.CORTEX_BOOKMARKS
            WHERE APP_ID = {self.APP_ID}
            AND BK_USERNAME = CURRENT_USER()
            AND BK_QUESTION = ?
        """
        session.sql(delete_query, (question,)).collect()

    def fetch_user_bookmarks(self):
        logging.info(f"fetch_user_bookmarks called in {__class__.__name__}")
        session = get_active_session()
        user_bookmarks_query = f"""
            SELECT BK_QUESTION 
            FROM VERTBAUDET.CHATBOT.CORTEX_BOOKMARKS
            WHERE APP_ID = {self.APP_ID}
            AND BK_USERNAME = CURRENT_USER()
            ORDER BY BK_UPDATED_AT DESC
        """
        user_bookmarks = session.sql(user_bookmarks_query).collect()
        return [row['BK_QUESTION'] for row in user_bookmarks]

    def insert_vote_data(self, question,vote_value):
        logging.info(f"Tentative d'ajout d'un vote : app_id={self.APP_ID}, question={question}, vote_value={vote_value}")
        session = get_active_session()
        try:
            query = f"""
                INSERT INTO VERTBAUDET.CHATBOT.CORTEX_VOTES 
                (VOTE_USERNAME, QUESTION_TEXT, VOTE_VALUE)
                VALUES (CURRENT_USER(), ?, ?)
            """
            session.sql(query, (question,vote_value)).collect()
            logging.info("Vote inséré avec succès")
            return True
        except Exception as e:
            logging.error(f"Erreur lors de l'ajout du vote: {str(e)}")
            return False

    def add_vote_button_up(self, question,  message_index):
        logging.info(f"add_vote_buttons")
        question_hash = hashlib.md5(question.encode()).hexdigest()
        like_button_key = f"like_{message_index}_{question_hash}"
        if st.button("👍", key=like_button_key):
            success = self.insert_vote_data(question, 1)
            if success:
                st.success("Vous avez aimé cette réponse !")
            else:
                st.error("Erreur lors de l'enregistrement du vote positif.")

    def add_vote_button_down(self, question,message_index):
        logging.info(f"add_vote_buttons")
        question_hash = hashlib.md5(question.encode()).hexdigest()
        dislike_button_key = f"dislike_{message_index}_{question_hash}"
        if st.button("👎", key=dislike_button_key):
            success = self.insert_vote_data(question,  -1)
            if success:
                st.success("Vous n'avez pas aimé cette réponse. Merci pour votre feedback !")
            else:
                st.error("Erreur lors de l'enregistrement du vote négatif.")

    def add_feedback_buttons(self, question, lang,  message_index):
        container = st.container()
        col1, col2, col3 = container.columns([1,1,1])
        with col1:
            self.add_bookmark_button(question, lang, message_index)
        with col2:
            self.add_vote_button_up(question, message_index)
        with col3:
            self.add_vote_button_down(question, message_index)
    
    def display_content(self, content: list, message_index: int = None, prompt: str = None):
        message_index = message_index or len(st.session_state.messages)
        for item in content:
            if item["type"] == "text":
                st.markdown(item["text"])
                self.add_feedback_buttons(prompt, "FR", message_index)
            # elif item["type"] == "suggestions":
            #     with st.expander("Suggestions", expanded=True):
            #         for suggestion_index, suggestion in enumerate(item["suggestions"]):
            #             unique_key = f"suggestion_{message_index}_{suggestion_index}_{hash(suggestion)}"
            #             if st.button(suggestion, key=unique_key):
            #                 st.session_state.active_suggestion = suggestion
            #                 st.experimental_rerun()

    # fonction qui génère une réponse en utilisant Cortex Complete basé sur le modèle sélectionné
    # @st.cache_data(show_spinner=False)
    
    def save_conversation(self,user_input, assistant_reply, model):
        try:
        # Obtenir la session Snowflake active
            session = get_active_session()
        
            # Insérer la conversation
            session.sql("""
            INSERT INTO CORTEX_CONVERSATION_HISTORY 
            (user_input, assistant_reply, model) 
            VALUES (?, ?, ?)
            """, [user_input, assistant_reply, model]).collect()
        
        except Exception as e:
            st.error(f"Erreur de sauvegarde dans Snowflake : {e}")
        
    def generate_response(self,user_input, model):      
        try:
            session = get_active_session()
        
            # prompt
            system_prompt = """
            You are a specialized AI assistant trained in Streamlit.
            You are helpful, direct, and focused on providing clear information.
            Your responses should be concise and informative.
            """
        
            # Combine system prompt with user input
            full_prompt = f"{system_prompt}\n\nUser: {user_input}\n\nAssistant:"
        
            # Generate response using Cortex based on selected model
            if model == "mistral-large2":
                response = session.sql(
                    "SELECT snowflake.cortex.complete('mistral-large2', :1) AS result", 
                    [full_prompt]
                ).collect()[0]['RESULT']
                return response        
            elif model == "llama3.1-70b":
                response = session.sql(
                    "SELECT snowflake.cortex.complete('llama3.1-70b', :1) AS result", 
                    [full_prompt]
                ).collect()[0]['RESULT']
                return response            
            else:
                response = "Je suis désolé, je ne comprends pas votre requête."        
                print(f"Default response: {response}") 
                return response.strip()  
        except Exception as e:
            st.error(f"Erreur lors de la génération de la réponse : {e}")
            return f"Une erreur est survenue lors du traitement de votre requête : {str(e)}"
        
    # Fonction qui traite le message/question saisi(e) par l'utilisateur
    # @st.cache_data(show_spinner=False)
    def process_message(self, prompt: str, model: str):
        if prompt:
            user_input = prompt.strip().lower()
            # Ajouter la requête de l'utilisateur à l'historique
            st.session_state.conversation_history.append({"role": "user", "content": user_input})
    
            try:
                with st.chat_message("assistant"):
                    # with st.spinner("Generating response..."):
                        assistant_reply = self.generate_response(user_input, model)

                        st.session_state.conversation_history.append({"role": "assistant", "content": assistant_reply})
                        st.session_state.history.append({"role": "user", "content": user_input})
                        st.session_state.history.append({"role": "assistant", "content": assistant_reply})

                        # Sauvegarde dans Snowflake
                        self.save_conversation(user_input, assistant_reply, model)

            except Exception as e:
                logging.error(f"Error occurred: {e}")
                st.error(f"An error Error: {str(e)}")
                
    def clear_chat_history(self):
        st.session_state.messages = []
        st.session_state.history = []
        st.session_state.conversation_history = []
        st.session_state.prompt_count = 0
    
    def run(self):
        PROMPT_LIMIT = 5
        NUMBER_OF_MESSAGES_TO_DISPLAY = 20
        custom_css = """
        <style>
            /* Force le fond blanc et la visibilité des boutons */
            button[kind="secondary"] {
                background-color: white !important;
                color: black !important;
                border: 1px solid #cccccc !important;
                visibility: visible !important;
                opacity: 1 !important;
                display: inline-flex !important;
            }
        

        /* Style pour le conteneur des boutons */
            div[data-testid="column"] {
                opacity: 1 !important;
                visibility: visible !important;
            }
        
        /* Force la visibilité du texte dans les boutons */
            button[kind="secondary"] p {
                color: black !important;
                opacity: 1 !important;
                visibility: visible !important;
            }

        /* Assure que le conteneur des boutons est visible */
            div[data-testid="stHorizontalBlock"] {
                opacity: 1 !important;
                visibility: visible !important;
                #background-color: rgba(255, 255, 255, 0.1) !important;
            }
             .stSelectbox{
                 color: white;
                 font-weight: bold;
            }
            /* Style for chat input */
            .stChatInput {
                background-color: transparent !important;
                border: none !important;
            }
            .sidebar .block-container {
                color: white;
            }
            /* Style pour les messages de l'utilisateur */
            .stChatMessage {
                background-color: transparent !important;
            }

        </style>
        """
        st.markdown(custom_css, unsafe_allow_html=True)
        with st.sidebar:   
            model_name = st.selectbox('Select your model:',(
                                    'mistral-large2',
                                    'llama3.1-70b'), key="model_name")                                    
        
        st.session_state["model"] = model_name

        if 'messages' not in st.session_state:
            st.session_state.messages = []
        
        st.sidebar.button("Reset your conversation", on_click=self.clear_chat_history, key="clear_history_button")
        self.display_user_bookmarks()
            
        self.load_and_display_image()
        # self.display_key_questions()
        
        if "history" not in st.session_state:
            st.session_state.history = []
        if 'conversation_history' not in st.session_state:
            st.session_state.conversation_history = []
        if "prompt_count" not in st.session_state:
            st.session_state.prompt_count = 0
        
        st.markdown("""
            <style>
            .stChatInput > div {
                background-color: transparent !important;
            }
            </style>
        """, unsafe_allow_html=True)
            
        user_input = st.chat_input("Quelle est votre question ?")

        if st.session_state.prompt_count >= PROMPT_LIMIT:
            st.error("Prompt limit reached! Reset la conversation pour recommencer.")
        elif user_input:
            self.process_message(prompt=user_input,model=model_name) 
            st.session_state.prompt_count += 1    
                
        if not st.session_state.history:
            initial_bot_message = "Comment puis-je vous aider aujourd'hui ?"
            st.session_state.history.append({"role": "assistant", "content": initial_bot_message})  
        
        if "favorites" not in st.session_state:
            st.session_state["favorites"] = []
        
        for index, message in enumerate(st.session_state.history[-NUMBER_OF_MESSAGES_TO_DISPLAY:]):
                role = message["role"]
                #mettre le logo de l'utilisateur et l'utilisateur
                avatar_image = "images/Boot.png" if role == "assistant" else "images/You.png" if role == "user" else None
                with st.chat_message(role,avatar=avatar_image):
                    st.markdown(f'<span style="color: white;">{message["content"]}</span>', unsafe_allow_html=True)
                    # st.markdown(message["content"])
                    # Ajouter un bouton de favori si le message est de l'assistant
                    if role == "assistant" and st.session_state.prompt_count > 0:
                        previous_message = st.session_state.history[index - 1]
                        if previous_message["role"] == "user":  # Vérifie que le précédent message est une question de l'utilisateur
                            self.add_feedback_buttons(question=message["content"], lang="FR", message_index=index)
        # message_index = message_index or len(st.session_state.messages)
        # for item in content:
        #     if item["type"] == "text":
        #         st.markdown(item["text"])
        #         self.add_feedback_buttons(prompt, "FR", message_index)
        # for message_index, message in enumerate(st.session_state.messages):
        #     with st.chat_message(message["role"]):
        #         if message["role"] == "user":
        #             st.markdown(message["content"][0]["text"])
        #         elif message["role"] == "assistant" and st.session_state.prompt_count > 0:
        #             self.display_content(
        #                 content=message["content"],
        #                 message_index=message_index,
        #                 prompt=st.session_state.messages[message_index-1]["content"][0]["text"],
        #             )
        


def main():
    app = Ask1App()
    app.run()

if __name__ == "__main__":
    main()