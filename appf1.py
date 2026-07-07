import io
from datetime import datetime

import pandas as pd
import streamlit as st
import fastf1

st.set_page_config(page_title="UC00614 - Integrar sistemas de informação", layout="wide")

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
        
        # Formatar a data para exibir  (dia-mes e ano)
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
    
    # PROTEÇÃO: Se a agenda estiver vazia, interrompe a execução antes de dar KeyError
    if agenda.empty or "Ronda" not in agenda.columns:
        st.warning(f"Não foram encontrados Grandes Prémios válidos para o ano de {ano}.")
        return

    gp = st.selectbox("Grande Prémio", agenda["Grande Prémio"].unique())
    
    # Extração segura da ronda
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
    
def pagina_info():
    st.title("ℹ️ Informação da Aplicação")

    # Texto maior (usando ###) e em itálico (usando asteriscos)
    st.markdown(
        "### *Esta aplicação foi desenvolvida por: Liliana Mendes e Marcelo Alves.*"
    )



def main():
    st.sidebar.title("🏎Analítica de Dados F1 ")
    op = st.sidebar.radio("Menu", ["Calendário da Temporada", "Resultados por Grande Prémio","Informaçao da aplicação"])
    if op == "Calendário da Temporada":
        pagina_calendario()
    elif op == "Informaçao da aplicação":
        pagina_info()
    else:
        pagina_resultados()

if __name__ == "__main__":
    main()

