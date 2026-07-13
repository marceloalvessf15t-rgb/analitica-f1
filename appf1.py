import io
from datetime import datetime
import pandas as pd
import streamlit as st
import fastf1
import fastf1.plotting
import matplotlib.pyplot as plt
import json
import sys
import asyncio

async def obter_dados_fastf1_async(ano: int, pista: str, sessao: str):
    """
    Obtém uma sessão do FastF1 de forma assíncrona sem bloquear o loop principal.
    
    Identificadores de sessão válidos: 
    'FP1', 'FP2', 'FP3', 'Q' (Qualificação), 'S' (Sprint), 'SQ' ou 'R' (Corrida).
    """
    loop = asyncio.get_running_loop()
    
    # 1. Cria o objeto da sessão (operação leve)
    session = fastf1.get_session(ano, pista, sessao)
    
    # 2. Executa o session.load() (operação pesada de I/O) numa thread separada
    # Isso impede que a sua aplicação asdf ou API congele durante o download (50-100MB)
    await loop.run_in_executor(None, session.load)
    
    return session

from fastf1.exceptions import DataNotLoadedError, NoLapDataError

async def obter_dados_seguros(ano, pista, sessao):
    try:
        session = await obter_dados_fastf1_async(ano, pista, sessao)
        return { "sucesso": True, "evento": session.event['EventName'], "erro": None }
    except ValueError:
        return { "sucesso": False, "evento": None, "erro": "Parametros invalidos (ano/pista)" }
    except (DataNotLoadedError, NoLapDataError):
        return { "sucesso": False, "evento": None, "erro": "Dados nao disponiveis para esta sessao" }
    except Exception as e:
        return { "sucesso": False, "evento": None, "erro": f"Erro inesperado: {str(e)}" }










# Configuração da página Streamlit (deve ser o primeiro comando Streamlit)
st.set_page_config(page_title="Analítica de Dados F1", layout="wide")

# Inicialização do Cache em disco da FastF1 para acelerar buscas
try:
    fastf1.Cache.enable_cache("f1_cache")
except Exception:
    pass

def converter_para_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Dados")
    return output.getvalue()

@st.cache_data
def obter_calendario_ano(ano):
    try:
        schedule = fastf1.get_event_schedule(ano)
        if schedule.empty:
            return pd.DataFrame()
            
        schedule = schedule[schedule["EventFormat"] != "testing"]
        df = schedule[["RoundNumber", "EventName", "OfficialEventName", "Location", "Country", "EventDate"]].copy()
        
        # Formatar a data para exibir (dia-mes e ano)
        df["EventDate"] = pd.to_datetime(df["EventDate"]).dt.strftime('%d-%m-%Y')
        
        df.columns = ["Ronda", "Grande Prémio", "Nome Oficial do grande prémio", "Localidade", "País", "Data"]
        return df
    except Exception as e:
        st.error(f"Erro ao carregar calendário para o ano {ano}: {e}")
        return pd.DataFrame()

@st.cache_data
def obter_resultados_corrida(ano, ronda):
    try:
        session = fastf1.get_session(ano, ronda, "R")
        session.load(laps=False, telemetry=False, weather=False, messages=False)
        results = session.results
        if results.empty:
            return pd.DataFrame()
            
        rows = []
        for _, r in results.iterrows():
            pos = pd.to_numeric(r["Position"], errors="coerce")
            rows.append({
                "Posição": pos,
                "Nº": r["DriverNumber"],
                "Piloto": r["FullName"],
                "Escuderia": r["TeamName"],
                "Pontos": r["Points"],
                "Status": r["Status"]
            })
        return pd.DataFrame(rows).sort_values("Posição", na_position="last")
    except Exception as e:
        st.error(f"Erro ao carregar resultados da ronda {ronda}: {e}")
        return pd.DataFrame()

@st.cache_data
def obter_voltas_corrida(ano, ronda):
    """Função otimizada com cache para carregar e limpar dados das voltas da corrida."""
    try:
        session = fastf1.get_session(ano, ronda, "R")
        session.load(laps=True, telemetry=False, weather=False, messages=False)
        
        # Manter apenas as colunas necessárias para poupar memória na cache
        df_laps = session.laps[["Driver", "LapNumber", "LapTime"]].copy()
        df_laps["LapTimeSeconds"] = df_laps["LapTime"].dt.total_seconds()
        
        # Obter mapeamento de cores dos pilotos
        pilotos = df_laps["Driver"].unique()
        cores_pilotos = {}
        for p in pilotos:
            try:
                cores_pilotos[p] = fastf1.plotting.get_driver_color(p, session)
            except Exception:
                cores_pilotos[p] = "#FFFFFF" # Cor padrão branca se falhar
                
        return df_laps, cores_pilotos
    except Exception as e:
        st.error(f"Erro ao carregar voltas para a ronda {ronda}: {e}")
        return pd.DataFrame(), {}

def pagina_calendario():
    st.title("📅 Calendário")
    ano_max = datetime.now().year
    ano = st.selectbox("Temporada", list(range(ano_max, 1959, -1)))
    df = obter_calendario_ano(ano)
    if not df.empty:
        st.download_button("📥 Exportar Excel", converter_para_excel(df), f"F1_Calendario_{ano}.xlsx")
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Sem dados de calendário disponiveis para este ano.")

def pagina_resultados():
    st.title("🏁 Resultados")
    ano_max = datetime.now().year
    ano = st.selectbox("Ano", list(range(ano_max, 1959, -1)))
    
    agenda = obter_calendario_ano(ano)
    
    if agenda.empty or "Ronda" not in agenda.columns:
        st.warning(f"Não foram encontrados Grandes Prémios válidos para o ano de {ano}.")
        return

    gp = st.selectbox("Grande Prémio", agenda["Grande Prémio"].unique())
    
    ronda_linha = agenda.loc[agenda["Grande Prémio"] == gp, "Ronda"]
    if ronda_linha.empty:
        st.error("Não foi possível determinar a ronda deste Grande Prémio.")
        return
        
    ronda = int(ronda_linha.iloc[0])
    
    with st.spinner("A carregar classificação oficial..."):
        df = obter_resultados_corrida(ano, ronda)
        
    if df.empty:
        st.info("Resultados não disponíveis para esta corrida.")
        return
    
    pesquisa = st.text_input("Pesquisar piloto")
    if pesquisa:
        df = df[df["Piloto"].str.contains(pesquisa, case=False, na=False)]
        
    c1, c2, c3 = st.columns(3)
    c1.metric("Pilotos", len(df))
    c2.metric("Equipas", df["Escuderia"].nunique())
    if not df.empty:
        c3.metric("Vencedor", df.iloc[0]["Piloto"])
        
    st.bar_chart(df.set_index("Piloto")["Pontos"])
    st.download_button("📥 Exportar Excel", converter_para_excel(df), f"F1_Resultados_{ano}_{ronda}.xlsx")
    st.dataframe(df, use_container_width=True, hide_index=True)

def pagina_grafico_voltas():
    st.title("📈 Análise de Tempos de Volta")
    ano_max = datetime.now().year
    ano = st.selectbox("Escolha o Ano", list(range(ano_max, 1959, -1)), key="ano_voltas")
    
    agenda = obter_calendario_ano(ano)
    if agenda.empty or "Ronda" not in agenda.columns:
        st.warning(f"Não foram encontrados Grandes Prémios válidos para o ano de {ano}.")
        return

    gp = st.selectbox("Escolha o Grande Prémio", agenda["Grande Prémio"].unique(), key="gp_voltas")
    ronda_linha = agenda.loc[agenda["Grande Prémio"] == gp, "Ronda"]
    if ronda_linha.empty:
        st.error("Não foi possível determinar a ronda deste Grande Prémio.")
        return
    ronda = int(ronda_linha.iloc[0])

    with st.spinner("A processar telemetria das voltas..."):
        df_voltas, cores_pilotos = obter_voltas_corrida(ano, ronda)

    if df_voltas.empty:
        st.info("Dados de tempos de volta não disponíveis para esta corrida.")
        return

    lista_pilotos = list(df_voltas["Driver"].dropna().unique())
    
    col1, col2 = st.columns(2)
    with col1:
        piloto1 = st.selectbox("Piloto 1 (Linha Contínua)", lista_pilotos, index=0)
    with col2:
        piloto2 = st.selectbox("Piloto 2 (Linha Tracejada)", lista_pilotos, index=1 if len(lista_pilotos) > 1 else 0)

    # Filtrar voltas por piloto
    voltas_p1 = df_voltas[df_voltas["Driver"] == piloto1].copy()
    voltas_p2 = df_voltas[df_voltas["Driver"] == piloto2].copy()

    if voltas_p1.empty or voltas_p2.empty:
        st.warning("Um dos pilotos selecionados não tem voltas registadas nesta corrida.")
        return

    # Remover picos (Outliers superiores a 20% da mediana causados por Pit Stops)
    voltas_p1_f = voltas_p1[voltas_p1["LapTimeSeconds"] < voltas_p1["LapTimeSeconds"].median() * 1.2]
    voltas_p2_f = voltas_p2[voltas_p2["LapTimeSeconds"] < voltas_p2["LapTimeSeconds"].median() * 1.2]

    # Construção do Gráfico Matplotlib
    fastf1.plotting.setup_mpl(misc_mpl_mods=False)
    fig, ax = plt.subplots(figsize=(12, 5))
    
    cor_p1 = cores_pilotos.get(piloto1, "#FFFFFF")
    cor_p2 = cores_pilotos.get(piloto2, "#FFFFFF")
    
    ax.plot(voltas_p1_f["LapNumber"], voltas_p1_f["LapTimeSeconds"], label=piloto1, color=cor_p1, linewidth=2)
    ax.plot(voltas_p2_f["LapNumber"], voltas_p2_f["LapTimeSeconds"], label=piloto2, color=cor_p2, linewidth=2, linestyle="--")
    
    ax.set_title(f"Ritmo de Corrida: {piloto1} vs {piloto2} - {gp} ({ano})", fontsize=12)
    ax.set_xlabel("Número da Volta")
    ax.set_ylabel("Tempo por Volta (Segundos)")
    ax.invert_yaxis()  # Tempos menores (mais rápidos) ficam no topo
    ax.grid(True, linestyle=":", alpha=0.5)
    ax.legend(loc="upper right")
    
    st.pyplot(fig)

    # Exibição de Métricas
    m1, m2 = st.columns(2)
    with m1:
        st.metric(f"Melhor Volta de {piloto1}", f"{voltas_p1['LapTimeSeconds'].min():.3f}s")
    with m2:
        st.metric(f"Melhor Volta de {piloto2}", f"{voltas_p2['LapTimeSeconds'].min():.3f}s")

def pagina_info():
    st.title("ℹ️ Informação da Aplicação")
    st.info("### *Esta aplicação foi desenvolvida por: Liliana Mendes e Marcelo Alves.*")

def main_streamlit():
    st.sidebar.title("🏎️ Analítica de Dados F1")
    op = st.sidebar.radio("Menu", [
        "Calendário da Temporada", 
        "Resultados por Grande Prémio", 
        "Análise de Tempos de Volta", 
        "Informaçao da aplicação"
    ])
    
    if op == "Calendário da Temporada":
        pagina_calendario()
    elif op == "Resultados por Grande Prémio":
        pagina_resultados()
    elif op == "Análise de Tempos de Volta":
        pagina_grafico_voltas()
    elif op == "Informaçao da aplicação":
        pagina_info()

# FUNÇÃO ADAPTADA PARA CONVERSAR COM O C#
# FUNÇÃO ADAPTADA PARA CONVERSAR COM O C#
def processar_f1_para_csharp(ano, pista, sessao):
    try:
        # Carrega a sessão com base no nome do circuito enviado pelo C#
        session = fastf1.get_session(int(ano), pista, sessao)
        session.load(laps=False, telemetry=False, weather=False, messages=False)
        
        resultados = []
        for index, row in session.results.iterrows():
            # Proteção para garantir valores válidos de posição
            pos = int(row['Position']) if pd.notna(row['Position']) else 0
            if pos == 0: continue # Ignora posições inválidas
            
            resultados.append({
                "Posicao": pos,
                "Piloto": str(row['Abbreviation']) if pd.notna(row['Abbreviation']) else str(row['DriverNumber']),
                "Equipa": str(row['TeamName']),
                "Pontos": float(row['Points']) if pd.notna(row['Points']) else 0.0
            })
            
        # O C# vai ler este print JSON exato da consola
        print(json.dumps(resultados))
        
    except Exception as e:
        print(json.dumps([{"Posicao": 1, "Piloto": "ERRO", "Equipa": str(e), "Pontos": 0.0}]))

        
    except Exception as e:
        print(json.dumps([{"Posicao": 1, "Piloto": "ERRO", "Equipa": str(e), "Pontos": 0.0}]))

        
    except Exception as e:
        print(json.dumps([{"Posicao": 1, "Piloto": "ERRO", "Equipa": str(e), "Pontos": 0.0}]))

# FILTRO PRINCIPAL DE EXECUÇÃO
if __name__ == "__main__":
    # Se o C# passar argumentos (ex: python appf1.py 2024 Monaco R)
    if len(sys.argv) > 3:
        processar_f1_para_csharp(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        # Se for o Streamlit no servidor ou execução manual local
        main_streamlit()
