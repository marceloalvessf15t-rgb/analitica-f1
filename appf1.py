import io
from datetime import datetime
import pandas as pd
import streamlit as st
import fastf1
import json
import sys

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
    
def pagina_info():
    st.title(" Informação da Aplicação")
    st.info("### *Esta aplicação foi desenvolvida por: Liliana Mendes e Marcelo Alves.*")

def main_streamlit():
    st.sidebar.title("🏎Analítica de Dados F1 ")
    op = st.sidebar.radio("Menu", ["Calendário da Temporada", "Resultados por Grande Prémio","Informaçao da aplicação"])
    if op == "Calendário da Temporada":
        pagina_calendario()
    elif op == "Informaçao da aplicação":
        pagina_info()
    else:
        pagina_resultados()

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

# FILTRO PRINCIPAL DE EXECUÇÃO
if __name__ == "__main__":
    # Se o C# passar argumentos (ex: python appf1.py 2024 Monaco R)
    if len(sys.argv) > 3:
        processar_f1_para_csharp(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        # Se for o Streamlit no servidor ou execução manual local
        main_streamlit()

