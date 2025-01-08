import streamlit as st
import pandas as pd
import snowflake.snowpark.functions as F
from snowflake.snowpark.context import get_active_session
from PIL import Image
from snowflake.snowpark.types import StringType, BooleanType
import io, logging

from common.cvalues import DEFAULT_CORTEX_DB
from common.cvalues import DEFAULT_CORTEX_SCHEMA


def main():

    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)

    # Fonction pour charger une image depuis un stage Snowflake
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
    # Fonction pour charger les données d'une table
    def load_table_data(table_name):
        session = get_active_session()
        return session.table(f"{DEFAULT_CORTEX_DB}.{DEFAULT_CORTEX_SCHEMA}.{table_name}").to_pandas()

    # Fonction pour insérer une nouvelle application dans la table CORTEX_APPS
    def insert_new_app(app_name, app_logo_url, app_url, app_active, app_access_role, app_database, app_schema, app_stage):
        session = get_active_session()
        try:
            new_app_id = session.sql(f"SELECT COALESCE(MAX(APP_ID), 0) + 1 AS new_id FROM {DEFAULT_CORTEX_DB}.{DEFAULT_CORTEX_SCHEMA}.CORTEX_APPS").collect()[0]['NEW_ID']
            session.sql(f"""
                INSERT INTO {DEFAULT_CORTEX_DB}.{DEFAULT_CORTEX_SCHEMA}.CORTEX_APPS 
                (APP_ID, APP_NAME, APP_LOGO_URL, APP_URL, APP_ACTIVE, APP_ACCESS_ROLE, APP_DATABASE, APP_SCHEMA, APP_STAGE) 
                VALUES 
                ({new_app_id}, '{app_name}', '{app_logo_url}', '{app_url}', {app_active}, '{app_access_role}', '{app_database}', '{app_schema}', '{app_stage}')
            """).collect()
            st.success(f"✔️ Nouvelle application '{app_name}' ajoutée avec succès !")
        except Exception as e:
            st.error(f"❌ Erreur lors de l'ajout de l'application : {e}")

    def load_top_questions(app_id, limit=10, days=30):
        session = get_active_session()
        query = f"""
        SELECT INPUT_TEXT, COUNT(*) as QUESTION_COUNT, 
            AVG(ELAPSED_TIME) as AVG_ELAPSED_TIME,
            AVG(RESOLUTION_TIME) as AVG_RESOLUTION_TIME
        FROM {DEFAULT_CORTEX_DB}.{DEFAULT_CORTEX_SCHEMA}.CORTEX_LOGS
        WHERE APP_ID = {app_id}
        AND DATETIME >= DATEADD(day, -{days}, CURRENT_TIMESTAMP())
        GROUP BY INPUT_TEXT
        ORDER BY QUESTION_COUNT DESC
        LIMIT {limit}
        """
        result = session.sql(query).to_pandas()
        logger.debug(f"Columns in result: {result.columns}")  # Log pour déboguer
        return result

    # Fonction pour modifier une application dans la table CORTEX_APPS
    def update_app(app_id, app_name, app_logo_url, app_url, app_active, app_access_role, app_database, app_schema, app_stage):
        session = get_active_session()
        try:
            session.sql(f"""
                UPDATE {DEFAULT_CORTEX_DB}.{DEFAULT_CORTEX_SCHEMA}.CORTEX_APPS 
                SET APP_NAME = '{app_name}', APP_LOGO_URL = '{app_logo_url}', APP_URL = '{app_url}', 
                    APP_ACTIVE = {app_active}, APP_ACCESS_ROLE = '{app_access_role}', 
                    APP_DATABASE = '{app_database}', APP_SCHEMA = '{app_schema}', APP_STAGE = '{app_stage}' 
                WHERE APP_ID = {app_id}
            """).collect()
            st.success(f"✔️ Application '{app_name}' modifiée avec succès !")
        except Exception as e:
            st.error(f"❌ Erreur lors de la modification de l'application : {e}")

    # Fonction pour afficher les détails de l'application de manière plus attrayante
    def display_app_details(app, logo_image):
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col1:
            if logo_image:
                st.image(logo_image, width=100)
            else:
                st.write("Logo non disponible")
        
        with col2:
            st.subheader(app['APP_NAME'])
            st.write(f"**URL:** {app['APP_URL']}")
            st.write(f"**Base de données:** {app['APP_DATABASE']}")
            st.write(f"**Schéma:** {app['APP_SCHEMA']}")
        
        with col3:
            status_color = "green" if app['APP_ACTIVE'] else "red"
            st.markdown(f"**Statut:** <span style='color:{status_color};'>{'Actif' if app['APP_ACTIVE'] else 'Inactif'}</span>", unsafe_allow_html=True)
            st.write(f"**Rôle d'accès:** {app['APP_ACCESS_ROLE']}")


    def load_models(app_id):
        session = get_active_session()
        return session.table(f"{DEFAULT_CORTEX_DB}.{DEFAULT_CORTEX_SCHEMA}.CORTEX_MODELS").filter(F.col("APP_ID") == str(app_id)).to_pandas()


    def update_model(app_id, yaml_file, yaml_name, yaml_active):
        session = get_active_session()
        try:
            yaml_active_bool = yaml_active.lower() == 'true'
            session.sql(f"""
                UPDATE {DEFAULT_CORTEX_DB}.{DEFAULT_CORTEX_SCHEMA}.CORTEX_MODELS 
                SET CORTEX_YAML_FILE = '{yaml_file}', CORTEX_YAML_ACTIVE = {yaml_active_bool}
                WHERE APP_ID = '{app_id}' AND CORTEX_YAML_NAME = '{yaml_name}'
            """).collect()
            st.success(f"✔️ Modèle '{yaml_name}' modifié avec succès !")
        except Exception as e:
            st.error(f"❌ Erreur lors de la modification du modèle : {e}")

    # Fonction pour insérer un nouveau modèle dans la table CORTEX_MODELS
    def insert_new_model(app_id, yaml_file, yaml_name, yaml_active):
        session = get_active_session()
        try:
            yaml_active_bool = yaml_active.lower() == 'true'
            session.sql(f"""
                INSERT INTO {DEFAULT_CORTEX_DB}.{DEFAULT_CORTEX_SCHEMA}.CORTEX_MODELS 
                (APP_ID, CORTEX_YAML_FILE, CORTEX_YAML_NAME, CORTEX_YAML_ACTIVE) 
                VALUES 
                ('{app_id}', '{yaml_file}', '{yaml_name}', {yaml_active_bool})
            """).collect()
            st.success(f"✔️ Nouveau modèle '{yaml_name}' ajouté avec succès !")
        except Exception as e:
            st.error(f"❌ Erreur lors de l'ajout du modèle : {e}")

            
    def add_model(app_id):
        st.subheader("Ajouter un nouveau modèle")
        form_key = f"add_model_form_{app_id}"
        
        with st.form(key=form_key):
            yaml_file = st.text_input("Fichier YAML")
            yaml_name = st.text_input("Nom du modèle (CORTEX_YAML_NAME)")
            yaml_active = st.checkbox("Actif", value=True)
            
            col1, col2 = st.columns(2)
            with col1:
                submit_button = st.form_submit_button("Ajouter le modèle")
            with col2:
                cancel_button = st.form_submit_button("Annuler")

            if submit_button:
                if not yaml_file or not yaml_name or app_id is None:
                    st.error("Tous les champs sont requis. Veuillez remplir tous les champs.")
                    return

                yaml_active_str = str(yaml_active).lower()
                insert_new_model(app_id, yaml_file, yaml_name, yaml_active_str)
                st.experimental_rerun()

    def modify_model(model):
        st.subheader(f"Modifier le modèle {model['CORTEX_YAML_NAME']}")
        
        form_key = f"modify_model_form_{model['APP_ID']}_{model['CORTEX_YAML_NAME']}"
        
        with st.form(key=form_key):
            new_yaml_file = st.text_input("Fichier YAML", value=model['CORTEX_YAML_FILE'])
            new_yaml_active = st.checkbox("Actif", value=model['CORTEX_YAML_ACTIVE'])
            submit_button = st.form_submit_button("Modifier le modèle")

            if submit_button:
                yaml_active_str = str(new_yaml_active).lower()
                update_model(model['APP_ID'], new_yaml_file, model['CORTEX_YAML_NAME'], yaml_active_str)
                st.experimental_rerun()
                
    # Fonction pour charger les signets d'une application
    def load_bookmarks(app_id):
        session = get_active_session()
        query = f"""
            SELECT BK_ID, APP_ID, BK_USERNAME, BK_QUESTION, BK_LANG, BK_CREATED_AT, BK_UPDATED_AT
            FROM {DEFAULT_CORTEX_DB}.{DEFAULT_CORTEX_SCHEMA}.CORTEX_BOOKMARKS
            WHERE APP_ID = {app_id}
            ORDER BY BK_UPDATED_AT DESC
        """
        return session.sql(query).to_pandas()

    # Fonction pour supprimer un signet
    def delete_bookmark(bookmark_id):
        session = get_active_session()
        try:
            query = f"""
            DELETE FROM {DEFAULT_CORTEX_DB}.{DEFAULT_CORTEX_SCHEMA}.CORTEX_BOOKMARKS
            WHERE BK_ID = {bookmark_id}
            """
            session.sql(query).collect()
            return True
        except Exception as e:
            st.error(f"❌ Erreur lors de la suppression du signet: {str(e)}")
            return False

    # Fonction pour mettre à jour un signet
    def update_bookmark(bookmark_id, new_question, new_lang):
        session = get_active_session()
        try:
            query = f"""
            UPDATE {DEFAULT_CORTEX_DB}.{DEFAULT_CORTEX_SCHEMA}.CORTEX_BOOKMARKS
            SET BK_QUESTION = '{new_question}', BK_LANG = '{new_lang}', BK_UPDATED_AT = CURRENT_TIMESTAMP()
            WHERE BK_ID = {bookmark_id}
            """
            session.sql(query).collect()
            return True
        except Exception as e:
            st.error(f"❌ Erreur lors de la mise à jour du signet: {str(e)}")
            return False

    # Fonction pour modifier une application via un formulaire
    def modify_app(app):
        st.subheader(f"✏️ Modifier l'application {app['APP_NAME']}")
        form_key = f"modify_app_form_{app['APP_ID']}"
        
        # Initialisation de st.session_state si nécessaire
        if form_key not in st.session_state:
            st.session_state[form_key] = {}
        
        # Initialisation des champs du formulaire
        if 'APP_NAME' not in st.session_state[form_key]:
            st.session_state[form_key]['APP_NAME'] = app['APP_NAME']
        if 'APP_LOGO_URL' not in st.session_state[form_key]:
            st.session_state[form_key]['APP_LOGO_URL'] = app['APP_LOGO_URL']
        if 'APP_URL' not in st.session_state[form_key]:
            st.session_state[form_key]['APP_URL'] = app['APP_URL']
        if 'APP_ACTIVE' not in st.session_state[form_key]:
            st.session_state[form_key]['APP_ACTIVE'] = app['APP_ACTIVE']
        if 'APP_ACCESS_ROLE' not in st.session_state[form_key]:
            st.session_state[form_key]['APP_ACCESS_ROLE'] = app['APP_ACCESS_ROLE']
        if 'APP_DATABASE' not in st.session_state[form_key]:
            st.session_state[form_key]['APP_DATABASE'] = app['APP_DATABASE']
        if 'APP_SCHEMA' not in st.session_state[form_key]:
            st.session_state[form_key]['APP_SCHEMA'] = app['APP_SCHEMA']
        if 'APP_STAGE' not in st.session_state[form_key]:
            st.session_state[form_key]['APP_STAGE'] = app['APP_STAGE']
        
        # Formulaire de modification
        with st.form(key=form_key + "_form"):
            new_name = st.text_input("Nom de l'application", value=st.session_state[form_key]['APP_NAME'])
            new_logo_url = st.text_input("URL du logo", value=st.session_state[form_key]['APP_LOGO_URL'])
            new_app_url = st.text_input("URL de l'application", value=st.session_state[form_key]['APP_URL'])
            new_active = st.checkbox("Actif", value=st.session_state[form_key]['APP_ACTIVE'])
            new_access_role = st.text_input("Rôle d'accès", value=st.session_state[form_key]['APP_ACCESS_ROLE'])
            new_database = st.text_input("Base de données", value=st.session_state[form_key]['APP_DATABASE'])
            new_schema = st.text_input("Schéma", value=st.session_state[form_key]['APP_SCHEMA'])
            new_stage = st.text_input("Stage", value=st.session_state[form_key]['APP_STAGE'])
            
            col1, col2 = st.columns([1, 1])
            with col1:
                submit_button = st.form_submit_button("Modifier l'application")
            with col2:
                cancel_button = st.form_submit_button("Annuler")

            if submit_button:
                success = update_app(app['APP_ID'], new_name, new_logo_url, new_app_url, new_active, new_access_role, new_database, new_schema, new_stage)
                if success:
                    st.success("✔️ Application modifiée avec succès!")
                    # Fermer le formulaire en supprimant la clé de session_state
                    del st.session_state[form_key]
                    st.experimental_rerun()
                else:
                    st.error("❌ Erreur lors de la modification de l'application.")

            if cancel_button:
                del st.session_state[form_key]
                st.experimental_rerun()

    # Style général avec CSS personnalisé
    st.markdown(
        """
        <style>
        .stTabs > div > div {
            font-size: 18px;
        }
        .stTextInput>div>div>input {
            border: 2px solid #1E90FF;
            border-radius: 10px;
            padding: 5px;
        }
        .stTextInput>div>div>input:focus {
            outline: none;
            border-color: #4682B4;
        }
        .stMarkdown h1, h2, h3 {
            color: #1E90FF;
        }
        .stAlert>div {
            border-radius: 10px;
            padding: 10px;
            background-color: #4682B4;
            color: white;
            font-weight: bold;
        }
        </style>
        """, 
        unsafe_allow_html=True
    )

    current_role = get_current_role()
    st.write(current_role)
    if current_role not in ["ASK1_ADMIN"]:
        st.warning("Vous n'avez pas les permissions nécessaires pour afficher cette page.")
        return  # Stoppe l'exécution de la page si l'utilisateur n'a pas le bon rôle
    # Titre de la page d'administration
    st.markdown("<h1>🎛️ Page d'administration Cortex</h1>", unsafe_allow_html=True)

    # Ajouter une application avant les onglets des applications
    if st.button("➕ Ajouter une application"):
        st.session_state.show_add_form = True

    if st.session_state.get("show_add_form", False):
        st.subheader("➕ Ajouter une nouvelle application")
        with st.form(key="add_app_form"):
            new_name = st.text_input("Nom de l'application")
            new_logo_url = st.text_input("URL du logo")
            new_app_url = st.text_input("URL de l'application")
            new_active = st.checkbox("Actif", value=True)
            new_access_role = st.text_input("Rôle d'accès")
            new_database = st.text_input("Base de données")
            new_schema = st.text_input("Schéma")
            new_stage = st.text_input("Stage")
            
            col1, col2 = st.columns([1, 1])
            with col1:
                submit_button = st.form_submit_button("Ajouter l'application")
            with col2:
                cancel_button = st.form_submit_button("Annuler")

            if submit_button:
                insert_new_app(new_name, new_logo_url, new_app_url, new_active, new_access_role, new_database, new_schema, new_stage)
                st.session_state.show_add_form = False
                st.experimental_rerun()

            if cancel_button:
                st.session_state.show_add_form = False
                st.experimental_rerun()

    # Chargement et filtrage des données d'applications
    apps_data = load_table_data("CORTEX_APPS")
    apps_data_filtered = apps_data[~apps_data['APP_ID'].isin([4, 5])]
    apps_data_filtered = apps_data_filtered.sort_values(by='APP_ID', ascending=True)

    # Ajout des icônes spécifiques pour Monitoring et Admin
    def get_app_icon(app_name):
        if "monitoring" in app_name.lower():
            return "📊"  # Icone pour Monitoring
        elif "Admin" in app_name.lower():
            return "🛠️"  # Icone pour Admin
        else:
            return "🤖"  # Icone par défaut pour les autres applications

    # Création des onglets principaux pour chaque application avec l'icône appropriée
    app_tabs = st.tabs([f"{get_app_icon(app['APP_NAME'])} {app['APP_NAME']}" for _, app in apps_data_filtered.iterrows()])

    # Boucle pour afficher les informations de chaque application dans son onglet respectif
    for (index, app), app_tab in zip(apps_data_filtered.iterrows(), app_tabs):
        with app_tab:
            st.markdown(f"### {app['APP_NAME']}")
            
            # Afficher les détails pour toutes les applications
            st.subheader(f"Détails de {app['APP_NAME']}")
            logo_image = load_image_from_snowflake(app["APP_LOGO_URL"])
            display_app_details(app, logo_image)

            # Bouton pour modifier l'application (pour toutes les applications)
            if st.button("✏️ Modifier l'application", key=f"modify_btn_{app['APP_ID']}"):
                st.session_state[f"modify_app_form_{app['APP_ID']}"] = {}

            # Afficher le formulaire de modification si le bouton est cliqué
            if f"modify_app_form_{app['APP_ID']}" in st.session_state:
                modify_app(app)

            # Vérifier si l'application n'est pas Monitoring ou Admin pour afficher les sous-onglets supplémentaires
            if "monitoring" not in app['APP_NAME'].lower() and "Admin" not in app['APP_NAME'].lower():
                # Afficher les sous-onglets Modèles et Signets seulement pour les autres applications
                subtab2, subtab3, subtab4 = st.tabs([f"📊 Modèles", f"🔖 Signets", f"❓ Questions"])
                
                # Sous-onglet 2 : Gestion des modèles
                with subtab2:
                    st.subheader(f"Modèles de {app['APP_NAME']}")
                    
                    # Afficher et gérer les modèles existants
                    models = load_models(app['APP_ID'])
                    for _, model in models.iterrows():
                        with st.expander(f"Modèle: {model['CORTEX_YAML_NAME']}"):
                            col1, col2, col3 = st.columns([2, 1, 1])
                            with col1:
                                st.write(f"Fichier: {model['CORTEX_YAML_FILE']}")
                            with col2:
                                status = "Actif" if model['CORTEX_YAML_ACTIVE'] else "Inactif"
                                st.write(f"Statut: {status}")
                            with col3:
                                if st.button("✏️ Modifier", key=f"modify_model_btn_{app['APP_ID']}_{model['CORTEX_YAML_NAME']}"):
                                    st.session_state[f"modify_model_{app['APP_ID']}_{model['CORTEX_YAML_NAME']}"] = True
                            
                            if st.session_state.get(f"modify_model_{app['APP_ID']}_{model['CORTEX_YAML_NAME']}", False):
                                with st.form(key=f"modify_model_form_{app['APP_ID']}_{model['CORTEX_YAML_NAME']}"):
                                    new_yaml_file = st.text_input("Fichier YAML", value=model['CORTEX_YAML_FILE'])
                                    new_yaml_active = st.checkbox("Actif", value=model['CORTEX_YAML_ACTIVE'])
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        if st.form_submit_button("Enregistrer"):
                                            update_model(app['APP_ID'], new_yaml_file, model['CORTEX_YAML_NAME'], str(new_yaml_active))
                                            st.session_state[f"modify_model_{app['APP_ID']}_{model['CORTEX_YAML_NAME']}"] = False
                                            st.experimental_rerun()
                                    with col2:
                                        if st.form_submit_button("Annuler"):
                                            st.session_state[f"modify_model_{app['APP_ID']}_{model['CORTEX_YAML_NAME']}"] = False
                                            st.experimental_rerun()
                    
                    # Bouton pour ajouter un nouveau modèle
                    if st.button("➕ Ajouter un modèle", key=f"add_model_btn_{app['APP_ID']}"):
                        st.session_state[f"add_model_{app['APP_ID']}"] = True
                    
                    if st.session_state.get(f"add_model_{app['APP_ID']}", False):
                        with st.form(key=f"add_model_form_{app['APP_ID']}"):
                            new_yaml_name = st.text_input("Nom du modèle")
                            new_yaml_file = st.text_input("Fichier YAML")
                            new_yaml_active = st.checkbox("Actif", value=True)
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.form_submit_button("Ajouter"):
                                    insert_new_model(app['APP_ID'], new_yaml_file, new_yaml_name, str(new_yaml_active))
                                    st.session_state[f"add_model_{app['APP_ID']}"] = False
                                    st.experimental_rerun()
                            with col2:
                                if st.form_submit_button("Annuler"):
                                    st.session_state[f"add_model_{app['APP_ID']}"] = False
                                    st.experimental_rerun()

                # Sous-onglet 3 : Gestion des signets
                with subtab3:
                    st.subheader(f"Signets de {app['APP_NAME']}")
                    bookmarks = load_bookmarks(app['APP_ID'])
                    if bookmarks.empty:
                        st.info(f"Aucun signet trouvé pour l'application sélectionnée (APP_ID: {app['APP_ID']}).")
                    else:
                        for _, bookmark in bookmarks.iterrows():
                            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                            with col1:
                                new_question = st.text_input("Question", value=bookmark['BK_QUESTION'], key=f"q_{bookmark['BK_ID']}_{app['APP_ID']}")
                            with col2:
                                new_lang = st.text_input("Langue", value=bookmark['BK_LANG'], key=f"l_{bookmark['BK_ID']}_{app['APP_ID']}")
                            with col3:
                                if st.button("✔️", key=f"update_{bookmark['BK_ID']}_{app['APP_ID']}"):
                                    if update_bookmark(bookmark['BK_ID'], new_question, new_lang):
                                        st.success("✔️ Signet mis à jour avec succès!")
                                        st.experimental_rerun()
                                    else:
                                        st.error("❌ Erreur lors de la mise à jour du signet.")
                            with col4:
                                if st.button("🗑️", key=f"delete_{bookmark['BK_ID']}_{app['APP_ID']}"):
                                    if delete_bookmark(bookmark['BK_ID']):
                                        st.success("✔️ Signet supprimé avec succès!")
                                        st.experimental_rerun()
                                    else:
                                        st.error("❌ Erreur lors de la suppression du signet.")
                with subtab4:
                    st.subheader(f"Questions fréquentes de {app['APP_NAME']}")
                    
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        days = st.slider("Période (jours)", 
                                        min_value=1, 
                                        max_value=365, 
                                        value=30, 
                                        step=1, 
                                        key=f"days_slider_{app['APP_ID']}")
                    with col2:
                        limit = st.number_input("Nombre de questions", 
                                                min_value=1, 
                                                max_value=100, 
                                                value=10, 
                                                step=1, 
                                                key=f"limit_input_{app['APP_ID']}")
                    
                    top_questions = load_top_questions(app['APP_ID'], limit, days)
                    
                    if top_questions.empty:
                        st.info(f"Aucune question trouvée pour l'application sélectionnée (APP_ID: {app['APP_ID']}) dans la période spécifiée.")
                    else:
                        st.write("Colonnes dans le DataFrame:", top_questions.columns)  # Affichage pour déboguer
                        for index, row in top_questions.iterrows():
                            st.write(f"{index + 1}. **{row['INPUT_TEXT']}**")
                            st.write(f"   - Nombre de fois posée : {row['QUESTION_COUNT']}")
                            st.write(f"   - Temps moyen d'exécution : {row['AVG_ELAPSED_TIME']:.2f} secondes")
                            st.write(f"   - Temps moyen de résolution : {row['AVG_RESOLUTION_TIME']:.2f} secondes")
                        st.write("---")
# Condition pour exécuter main() si le script est exécuté directement
if __name__ == "__main__":
    main()
