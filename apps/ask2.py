def get_similar_chunks (question):

    cmd = """
        with results as
        (SELECT RELATIVE_PATH,
        VECTOR_COSINE_SIMILARITY(docs_chunks_table.chunk_vec,
                    SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', ?)) as similarity,
        chunk
        from afp.docs.docs_chunks_table
        order by similarity desc
        limit ?)
        select chunk, relative_path from results 
    """
    
    df_chunks = st.session_state.session.sql(cmd, params=[question, 5]).to_pandas()       

    df_chunks_lenght = len(df_chunks) -1

    similar_chunks = ""
    for i in range (0, df_chunks_lenght):
        similar_chunks += df_chunks._get_value(i, 'CHUNK')

    similar_chunks = similar_chunks.replace("'", "")
            
    return similar_chunks

def summarize_question_with_history(chat_history, question):
# To get the right context, use the LLM to first summarize the previous conversation
# This will be used to get embeddings and find similar chunks in the docs for context

    prompt = f"""
        Based on the chat history below and the question, generate a query that extend the question
        with the chat history provided. The query should be in natual language. 
        Answer with only the query. Do not add any explanation.
        
        <chat_history>
        {chat_history}
        </chat_history>
        <question>
        {question}
        </question>
        """
    
    cmd = """
            select snowflake.cortex.complete(?, ?) as response
        """
    df_response = st.session_state.session.sql(cmd, params=[st.session_state.model_name, prompt]).collect()
    sumary = df_response[0].RESPONSE     

    if st.session_state.debug:
        st.sidebar.text("Summary to be used to find similar chunks in the docs:")
        st.sidebar.caption(sumary)

    sumary = sumary.replace("'", "")

    return sumary

def create_prompt (myquestion):

    if st.session_state.use_chat_history:
        chat_history = get_chat_history()

        if chat_history != []: #There is chat_history, so not first question
            question_summary = summarize_question_with_history(chat_history, myquestion)
            prompt_context =  get_similar_chunks(question_summary)
        else:
            prompt_context = get_similar_chunks(myquestion) #First question when using history
    else:
        prompt_context = get_similar_chunks(myquestion)
        chat_history = ""

    prompt = f"""
        You are an expert chat assistance that extracs information from the CONTEXT provided
        between <context> and </context> tags.
        You offer a chat experience considering the information included in the CHAT HISTORY
        provided between <chat_history> and </chat_history> tags..
        When ansering the question contained between <question> and </question> tags
        be concise and do not hallucinate. 
        If you don´t have the information just say so.
        
        Do not mention the CONTEXT used in your answer.
        Do not mention the CHAT HISTORY used in your asnwer.
        
        <chat_history>
        {chat_history}
        </chat_history>
        <context>          
        {prompt_context}
        </context>
        <question>  
        {myquestion}
        </question>
        Answer: 
        """

    return prompt

def page():
    # Default application settings

        st.title(f":speech_balloon: Chat Document Assistant with Snowflake Cortex")
        st.write("This is the list of documents you already have and that will be used to answer your questions:")
        docs_available = st.session_state.session.sql("ls @afp.docs.docs").collect()
        list_docs = []
        for doc in docs_available:
            list_docs.append(doc["name"])

        # Create two columns
        col1, col2 = st.columns([3,1])

        with col1:
            st.dataframe(list_docs)
        with col2:
            st.markdown('<div class="vertically-centered">', unsafe_allow_html=True)
            # Add the link button to upload a new document via Snowflake UI
            upload_url = "https://app.snowflake.com/svbwrkv/devoteam_beta/#/data/databases/AFP/schemas/DOCS/stage/DOCS"
            st.markdown(
                f'<a href="{upload_url}" target="_blank">'
                f'<button style="background-color:#4CAF50;color:white;padding:10px 20px;border:none;border-radius:5px;">Add New File</button></a>',
                unsafe_allow_html=True
            )
            st.markdown('</div>', unsafe_allow_html=True)

        # Button to refresh and update DOCS_CHUNKS_TABLE after uploading
        if st.button("PARSING->CHUNKING->VETORIZING->INDEXING", key="refresh_update_button"):
            try:
                # Refresh the stage
                refresh_stage_cmd = f"ALTER STAGE {DATABASE}.{SCHEMA_PUBLIC}.{STAGE_DOCS} REFRESH;"
                st.session_state.session.sql(refresh_stage_cmd).collect()
                st.success("Stage has been refreshed.")

                # Truncate the existing table
                truncate_cmd = f"TRUNCATE TABLE {DATABASE}.{SCHEMA_PUBLIC}.DOCS_CHUNKS_TABLE;"
                st.session_state.session.sql(truncate_cmd).collect()
                st.success("Table has been truncated.")

                # Perform the direct insert with fully qualified stage name
                insert_cmd = f"""
                INSERT INTO {DATABASE}.{SCHEMA_PUBLIC}.DOCS_CHUNKS_TABLE (relative_path, size, file_url, scoped_file_url, chunk, chunk_vec)
                SELECT 
                    relative_path,
                    size,
                    file_url,
                    build_scoped_file_url(@{DATABASE}.{SCHEMA_PUBLIC}.{STAGE_DOCS}, relative_path) as scoped_file_url,
                    func.chunk as chunk,
                    SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', chunk) as chunk_vec
                FROM 
                    directory(@{DATABASE}.{SCHEMA_PUBLIC}.{STAGE_DOCS}),
                    TABLE({DATABASE}.{SCHEMA_PUBLIC}.pdf_text_chunker(build_scoped_file_url(@{DATABASE}.{SCHEMA_PUBLIC}.{STAGE_DOCS}, relative_path))) as func;
                """
                st.session_state.session.sql(insert_cmd).collect()
                st.success("Data has been inserted into the table successfully.")

            except Exception as e:
                st.error(f"Error during operation: {e}")

        config_options()
        init_messages()
        
        # Display chat messages from history on app rerun
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        
        # Accept user input
        if question := st.chat_input("What do you want to know about your products?"):
            # Add user message to chat history
            st.session_state.messages.append({"role": "user", "content": question})
            # Display user message in chat message container
            with st.chat_message("user"):
                st.markdown(question)
            # Display assistant response in chat message container
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
        
                question = question.replace("'","")
        
                with st.spinner(f"{st.session_state.model_name} thinking..."):
                    response = complete(question)
                    res_text = response[0].RESPONSE     
                
                    res_text = res_text.replace("'", "")
                    message_placeholder.markdown(res_text)
            
            st.session_state.messages.append({"role": "assistant", "content": res_text})

def complete(myquestion):

    prompt =create_prompt (myquestion)
    cmd = """
            select snowflake.cortex.complete(?, ?) as response
        """
    
    df_response = st.session_state.session.sql(cmd, params=[st.session_state.model_name, prompt]).collect()
    return df_response



num_chunks = 6
slide_window = 7
SIMILARITY_THRESHOLD = 0.75
SCHEMA_PUBLIC = "DOCS"
SCHEMA = "PUBLIC"
STAGE = "SEMANTIC"
STAGE_DOCS = "DOCS"
STAGE_SEMANTIC = "SEMANTIC"
DATABASE = "AFP"
FILE = "semantic.yaml"
suggestion = ['Try our suggestions']

def get_chat_history():
#Get the history from the st.session_stage.messages according to the slide window parameter
    
    chat_history = []
    
    start_index = max(0, len(st.session_state.messages) - 7)
    for i in range (start_index , len(st.session_state.messages) -1):
        chat_history.append(st.session_state.messages[i])

    return chat_history

    