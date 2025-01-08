import streamlit as st
import snowflake.snowpark.functions as F
from snowflake.snowpark.context import get_active_session
from PIL import Image
import io
import base64

# Import des applications spécifiques
from pages import Admin
# from apps.base_analyst_app import BaseAnalystApp
from apps.ask1 import Ask1App


def load_image_from_snowflake(stage_path):
    session = get_active_session()
    try:
        with session.file.get_stream(stage_path) as file_stream:
            image_data = file_stream.read()
            return Image.open(io.BytesIO(image_data))
    except Exception as e:
        st.error(f"Erreur lors du chargement de l'image : {e}")
        return None

def get_current_role():
    session = get_active_session()
    try:
        current_role_query = session.sql("SELECT CURRENT_ROLE()").collect()
        if current_role_query and len(current_role_query) > 0:
            return current_role_query[0][0]  # Récupère le rôle actif
        else:
            return None
    except Exception as e:
        st.error(f"Erreur lors de la récupération du rôle actif : {e}")
        return None
    
def get_user_roles(username):
    session = get_active_session()
    try:
        query = f"""
            SELECT ROLE
            FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS
            WHERE GRANTEE_NAME = '{username}'
        """
        roles_query = session.sql(query).collect()
        roles = [row['ROLE'] for row in roles_query]
        return roles
    except Exception as e:
        st.error(f"Erreur lors de la récupération des rôles de l'utilisateur : {e}")
        return []
    
def enforce_role(role):
    session = get_active_session()
    try:
        session.sql(f"USE ROLE {role}").collect()
        return True
    except Exception as e:
        st.error(f"Impossible de forcer le rôle {role} : {e}")
        return False
    
def load_css():
    st.markdown("""
    <style>
    
    .stApp {
       background-color: #8FBC8F;
   }
    [data-testid="stSidebar"] {
        background-color: #2c5836;
    }
    .stImage {
        border-radius: 15px;
        margin-bottom: 10px;
        justify-content: center;
        align-items: center;
        cursor: pointer;
        transition: transform 0.3s ease;
    }
    .stImage:hover {
    transform: scale(1.05);
    }
    .stButton>button {
        position: absolute;
        width: 100%;
        height: 100%;
        opacity: 0;
        cursor: pointer;
        z-index: 1;
    }
    .stButton>button:hover {
        background-color: #f0f0f0;
        box-shadow: 0px 6px 8px rgba(0, 0, 0, 0.2);
        transform: translateY(-2px);
    }
    .app-container {
        position: relative;
        display: flex;
        flex-direction: column;
        align-items: center;
        margin-bottom: 10px;
    }
    .header {
        display: block;
        margin-left: auto;
        margin-right: auto;
        width: 50%;
        background-color: transparent;
        
    }
    .header-text {
        color: white;
        font-size: 1.6rem;
        text-align: center;
        font-family: Calibri;
        margin: 1px 0;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

def main():
    st.set_page_config(page_title="CHATVBT", layout="wide", page_icon="🏠")
    load_css()
    
    session = get_active_session()
    # Récupérer le rôle actif de l'utilisateur
    current_role = get_current_role()
    username_query = session.sql("SELECT CURRENT_USER()").collect()
    username = username_query[0][0] if username_query else None
    user_roles = get_user_roles(username) if username else []
    st.write(current_role)
    st.write(user_roles)
    # Liste des rôles autorisés
    allowed_roles = ["ASK1_USER", "ASK1_ADMIN"]

    if "ACCOUNTADMIN" in user_roles and current_role != "ASK1_USER":
        st.error("Vous utilisez un rôle non autorisé. Veuillez vous connecter avec un rôle valide.")
        return
    if current_role not in allowed_roles:
        st.warning("Vous n'avez pas les permissions nécessaires pour accéder à ces fonctionnalités.")
        return
    if not enforce_role("ask1_user"):
        st.error("Impossible de forcer le rôle approprié. Veuillez contacter un administrateur.")
        return
    
    chatvbt_logo_path = "@RAW_DATA/CHATVBT/images/unnamed.png"  # Remplacez par le chemin réel
    chatvbt_logo = load_image_from_snowflake(chatvbt_logo_path)
    if chatvbt_logo:
        st.markdown('<div class="header">', unsafe_allow_html=True)
        st.image(chatvbt_logo, use_column_width=False)
        st.markdown('<div class="header-text">Choose your favorite ChatBot...</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    
    #st.title("CHATVBT")

    logo_width, logo_height = 1104, 294


    df = session.table("VERTBAUDET.CHATBOT.CORTEX_APPS").filter(F.col("APP_ACTIVE") == True).to_pandas()
    df = df.sort_values(by='APP_ID')

    cols = st.columns(3)

    # Parcours des applications dans le DataFrame
    for i, (_, app) in enumerate(df.iterrows()):
        col = cols[i % 3]
        with col:
            st.markdown('<div class="app-container">', unsafe_allow_html=True)
            logo_image = load_image_from_snowflake(app["APP_LOGO_URL"])
            if logo_image:
                resized_image = logo_image.resize((280, 80))
                # Afficher d'abord l'image
                st.image(resized_image, use_column_width=True)
                # Puis un bouton transparent par-dessus
                if st.button("Sélectionner", key=f"app_{i}", help="Cliquez pour accéder à l'application"):
                    st.session_state.selected_page = app["APP_URL"]
            st.markdown('</div>', unsafe_allow_html=True)
                #     st.image(resized_image, use_column_width=False)
                # if st.button(app['APP_NAME']):
                #     st.session_state.selected_page = app["APP_URL"]
                # st.markdown('</div>', unsafe_allow_html=True)


    if "selected_page" in st.session_state:
        try:
            page_mapping = {
                "ask1": Ask1App,
                # "monitoring": monitoring,
                "Admin": Admin
            }
            selected = st.session_state.selected_page
            if selected in page_mapping:
                if selected == "Admin":
                    page_mapping[selected].main()
                else:
                    # Pour les applications d'analyse, on instancie la classe et on appelle sa méthode run
                    app = page_mapping[selected]()
                    app.run()
            else:
                st.error("Page non trouvée")        
        except Exception as e:
            st.error(f"Le module pour l'application sélectionnée n'a pas été trouvé: {e}")
            st.info("Retourner à la page d'accueil en sélectionnant une autre application.")


if __name__ == "__main__":
    main()