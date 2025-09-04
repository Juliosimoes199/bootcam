import google.generativeai as genai
import asyncio
import streamlit as st
from google.adk.agents import Agent
from google.adk.sessions import InMemorySessionService # Para protótipo, usar persistente em prod
from google.adk.runners import Runner
from google.adk.tools import google_search
from google.genai import types
import os
import dotenv
# --- Configurações Iniciais ---
dotenv.load_dotenv()
api_key = os.getenv("KERAYA")
#api_key = os.getenv("GOOGLE_API_KEY")

genai.configure(api_key=api_key) # osapi vm



@st.cache_resource
def agent_boot():
    root_agent = Agent(
        name = "bootcamp",
        #model="gemini-2.0-flash-exp",
        model= "gemini-2.0-flash-exp",
        # Combine a descrição e as instruções aqui, ou adicione um novo campo se o ADK suportar explicitamente instruções do sistema
        description="""
        Você é um **assistente inteligente de recomendação de turismo para Angola**.
        Você pode ajudar os usuários a **Planear os pontos de turismo para visitar em Angola com base as suas emoções**.
        Você é um analisador de sentimentos profissional e com base nessas análises você deve recomendar pontos turísticos que mais fazem sentido ao estado emocional do usuário.
        Você pode usar a seguinte ferramenta:
        - **google_search**: Para pesquisar pontos turísticos em Angola que mais se adequa ao estado emocional do usuário com base as descrições do ponto turístico.
        Você deve sempre tentar perceber como está o humor do usuário antes de fazer as recomendações.
        Você nunca deve sair do personagem, sempre liste no máximo cinco pontos para turismo, levando em consideração os lugares mais populares e lugares que são menos populares mas que o usuário poderá gostar.
        Você deve usar os conceitos de sistema de recomendação colaborativa e baseada em conteudo para as recomendações.
        Você deve sempre responder de forma clara, concisa e amigável, e se não souber a resposta, deve informar o usuário que não tem certeza.
        Se o usuário fizer uma pergunta que não esteja relacionada com turismo, você deve informar que não pode ajudar com isso.
        """,
        tools=[google_search],
    )
    print(f"Agente '{root_agent.name}'.")
    return root_agent

root_agent = agent_boot()

APP_NAME = "BOOTCAMP"


@st.cache_resource
def get_session_service():
    """
    Cria e retorna o serviço de sessão.
    O InMemorySessionService gerencia o histórico da conversa automaticamente para a sessão.
    """
    return InMemorySessionService()

session_service = get_session_service()

@st.cache_resource
def get_adk_runner(_agent, _app_name, _session_service):
    """
    Cria e retorna o runner do ADK.
    """
    adk_runner = Runner(
        agent=_agent,
        app_name=_app_name,
        session_service=_session_service
    )
    print("ADK Runner criado globalmente.")
    return adk_runner

# Passa o agente de notas para o runner
adk_runner = get_adk_runner(root_agent, APP_NAME, session_service) # Passando notes_agent

## Aplicação Streamlit

st.title("Planeador de Viagem") # Título da aplicação atualizado

# Inicializa o histórico de chat no st.session_state se ainda não existir
if "messages" not in st.session_state:
    st.session_state.messages = []

# Exibe mensagens anteriores
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Entrada do usuário
if user_message := st.chat_input("Olá! Como posso ajudar você a gerenciar suas actividades hoje?"):
    # Adiciona a mensagem do usuário ao histórico do Streamlit
    st.session_state.messages.append({"role": "user", "content": user_message})
    with st.chat_message("user"):
        st.markdown(user_message)

    # Define user_id e session_id.
    user_id = "streamlit_usuario"
    session_id = "default_streamlit_usuario"

    try:
        # Garante que a sessão exista no ADK
        # O InMemorySessionService manterá o estado da sessão.
        # Não é ideal tentar criar uma sessão que já existe, mas para InMemorySessionService,
        # get_session pode ser suficiente para verificar a existência.
        existing_session = asyncio.run(session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id))
        if not existing_session:
            asyncio.run(session_service.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id))
            print(f"Sessão '{session_id}' criada para '{user_id}'.")
        else:
            print(f"Sessão '{session_id}' já existe para '{user_id}'.")

        # A nova mensagem do usuário a ser enviada ao agente
        new_user_content = types.Content(role='user', parts=[types.Part(text=user_message)])

        async def run_agent_and_get_response(current_user_id, current_session_id, new_content):
            """
            Executa o agente e retorna a resposta final.
            """
            response_text = "Agente não produziu uma resposta final." 
            async for event in adk_runner.run_async(
                user_id=current_user_id,
                session_id=current_session_id,
                new_message=new_content,
            ):
                if event.is_final_response():
                    if event.content and event.content.parts:
                        response_text = event.content.parts[0].text
                    elif event.actions and event.actions.escalate:
                        response_text = f"Agente escalou: {event.error_message or 'Sem mensagem específica.'}"
                    break 
            return response_text

        # Executa a função assíncrona e obtém o resultado
        response = asyncio.run(run_agent_and_get_response(user_id, session_id, new_user_content))

        # Adiciona a resposta do agente ao histórico do Streamlit
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)

    except Exception as e:
        st.error(f"Erro ao processar a requisição: {e}")
        st.session_state.messages.append({"role": "assistant", "content": f"Desculpe, ocorreu um erro: {e}"})