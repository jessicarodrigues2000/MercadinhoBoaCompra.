from datetime import timedelta
import hmac
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

st.set_page_config(
    page_title="Mercadinho Boa Compra",
    page_icon="🛒",
    layout="wide",
)

st.markdown("""
<style>
    .main {background-color: #f7f8fa;}
    [data-testid="stMetric"] {
        background: white; padding: 15px; border-radius: 12px;
        border: 1px solid #e7eaf0;
    }
    div.block-container {padding-top: 1.5rem;}
</style>
""", unsafe_allow_html=True)

PRODUTOS = [
    ("Arroz 5 kg", "Mercearia", 27.90),
    ("Feijão 1 kg", "Mercearia", 8.49),
    ("Macarrão 500 g", "Mercearia", 5.49),
    ("Óleo 900 ml", "Mercearia", 7.99),
    ("Açúcar 1 kg", "Mercearia", 4.79),
    ("Café 500 g", "Mercearia", 18.90),
    ("Farinha 1 kg", "Mercearia", 6.29),
    ("Leite 1 L", "Laticínios", 5.29),
    ("Queijo 300 g", "Laticínios", 13.90),
    ("Iogurte", "Laticínios", 3.49),
    ("Refrigerante 2 L", "Bebidas", 9.49),
    ("Água 1,5 L", "Bebidas", 3.29),
    ("Suco 1 L", "Bebidas", 7.49),
    ("Biscoito", "Mercearia", 4.59),
    ("Pão de forma", "Padaria", 8.99),
    ("Detergente", "Limpeza", 2.79),
    ("Sabão em pó", "Limpeza", 12.90),
    ("Papel higiênico", "Higiene", 17.90),
    ("Shampoo", "Higiene", 14.90),
    ("Creme dental", "Higiene", 5.99),
]


@st.cache_data
def gerar_dados():
    """Gera dados sintéticos reproduzíveis para a demonstração acadêmica."""
    rng = np.random.default_rng(42)
    datas = pd.date_range(end=pd.Timestamp.today().normalize() - pd.Timedelta(days=1),
                          periods=730, freq="D")
    linhas = []

    for nome, categoria, preco_base in PRODUTOS:
        estoque = int(rng.integers(45, 100))
        minimo = max(10, int(estoque * 0.25))
        fator_produto = rng.uniform(0.7, 1.35)

        for data in datas:
            dia = data.dayofweek
            fator_semana = 1.25 if dia in (4, 5) else (0.82 if dia == 0 else 1.0)
            fator_mes = 1.12 if data.month in (12, 1) else 1.0
            media = 7.0 * fator_produto * fator_semana * fator_mes
            procura = max(0, int(round(rng.poisson(media))))
            entrada = 0

            # Reposição simulada quando o estoque fica baixo.
            if estoque < minimo + 12:
                entrada = int(rng.integers(25, 65))
                estoque += entrada

            estoque_inicial = estoque
            vendido = min(procura, estoque)
            estoque = max(0, estoque - vendido)
            preco = round(preco_base * rng.uniform(0.97, 1.04), 2)
            leitura_sensor = max(0, round(estoque + rng.normal(0, 1.5), 1))

            linhas.append({
                "data": data,
                "produto": nome,
                "categoria": categoria,
                "preco_unitario": preco,
                "quantidade_vendida": vendido,
                "faturamento": round(preco * vendido, 2),
                "estoque_inicial": estoque_inicial,
                "quantidade_recebida": entrada,
                "estoque_final": estoque,
                "estoque_minimo": minimo,
                "leitura_iot_simulada": leitura_sensor,
            })

    return pd.DataFrame(linhas)


def dinheiro(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# Persistência: Supabase quando configurado; CSV local para testes no computador.
ARQUIVO_ESTOQUE = Path(__file__).resolve().parent / "estoque_atual.csv"


def cliente_supabase():
    """Retorna o cliente Supabase usando a chave pública."""
    try:
        cfg = st.secrets.get("supabase", {})
        url = cfg.get("url", "")
        key = cfg.get("service_role_key", "")

        if url and key:
            from supabase import create_client
            return create_client(url, key)

    except Exception as erro:
        st.warning(f"Não foi possível conectar ao Supabase: {erro}")

    return None

SUPABASE = cliente_supabase()


def estoque_inicial_historico(df_historico):
    mais_recente = df_historico.sort_values("data").groupby("produto", as_index=False).tail(1)
    estoque = mais_recente[["produto", "categoria", "preco_unitario", "estoque_final", "estoque_minimo"]].copy()
    estoque = estoque.rename(columns={"estoque_final": "estoque_atual"})
    estoque["estoque_atual"] = estoque["estoque_atual"].astype(int)
    estoque["estoque_minimo"] = estoque["estoque_minimo"].astype(int)
    return estoque[["produto", "categoria", "preco_unitario", "estoque_atual", "estoque_minimo"]]


def carregar_estoque(df_historico):
    """Carrega o catálogo e o estoque do Supabase ou, em modo local, do CSV."""
    if SUPABASE is not None:
        try:
            resposta = SUPABASE.table("products").select("*").execute()
            if resposta.data:
                estoque = pd.DataFrame(resposta.data)
                return estoque[["produto", "categoria", "preco_unitario", "estoque_atual", "estoque_minimo"]]
            inicial = estoque_inicial_historico(df_historico)
            SUPABASE.table("products").upsert(inicial.to_dict(orient="records"), on_conflict="produto").execute()
            return inicial
        except Exception as exc:
            st.error("Não foi possível acessar o banco online. Confira as credenciais e a tabela products no Supabase.")
            st.exception(exc)
            st.stop()

    if ARQUIVO_ESTOQUE.exists():
        estoque = pd.read_csv(ARQUIVO_ESTOQUE)
        colunas = ["produto", "categoria", "preco_unitario", "estoque_atual", "estoque_minimo"]
        if all(coluna in estoque.columns for coluna in colunas):
            estoque["estoque_atual"] = pd.to_numeric(estoque["estoque_atual"], errors="coerce").fillna(0).clip(lower=0).astype(int)
            estoque["estoque_minimo"] = pd.to_numeric(estoque["estoque_minimo"], errors="coerce").fillna(5).clip(lower=0).astype(int)
            estoque["preco_unitario"] = pd.to_numeric(estoque["preco_unitario"], errors="coerce").fillna(0).clip(lower=0).round(2)
            return estoque[colunas]

    estoque = estoque_inicial_historico(df_historico)
    estoque.to_csv(ARQUIVO_ESTOQUE, index=False, encoding="utf-8-sig")
    return estoque


def salvar_estoque(estoque):
    colunas = ["produto", "categoria", "preco_unitario", "estoque_atual", "estoque_minimo"]
    dados = estoque[colunas].copy()
    dados["estoque_atual"] = pd.to_numeric(dados["estoque_atual"], errors="raise").astype(int)
    dados["estoque_minimo"] = pd.to_numeric(dados["estoque_minimo"], errors="raise").astype(int)
    dados["preco_unitario"] = pd.to_numeric(dados["preco_unitario"], errors="raise").round(2)
    if SUPABASE is not None:
        SUPABASE.table("products").upsert(dados.to_dict(orient="records"), on_conflict="produto").execute()
    else:
        dados.to_csv(ARQUIVO_ESTOQUE, index=False, encoding="utf-8-sig")


def verificar_login():
    """Login simples para a demonstração; credenciais ficam nos Secrets do servidor."""
    try:
        usuarios = st.secrets.get("users", {})
    except Exception:
        usuarios = {}
    if not usuarios:
        st.title("🛒 Mercadinho Boa Compra")
        st.error("O login ainda não foi configurado.")
        st.markdown("Crie `.streamlit/secrets.toml` usando o modelo `secrets.toml.example` incluído no projeto. Para publicar, configure os mesmos valores em **App settings → Secrets** da hospedagem.")
        st.stop()

    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False
    if st.session_state.autenticado:
        return

    st.title("🛒 Mercadinho Boa Compra")
    st.subheader("Entrar no sistema")
    with st.form("login_form"):
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar", type="primary", use_container_width=True)
    if entrar:
        senha_correta = usuarios.get(usuario, "")
        if senha_correta and hmac.compare_digest(str(senha), str(senha_correta)):
            st.session_state.autenticado = True
            st.session_state.usuario = usuario
            st.rerun()
        else:
            st.error("Usuário ou senha incorretos.")
    st.caption("Protótipo acadêmico. Não reutilize senhas pessoais neste sistema.")
    st.stop()


def preparar_features(serie):
    df = serie[["data", "quantidade_vendida"]].copy().sort_values("data")
    df["dia_semana"] = df["data"].dt.dayofweek
    df["mes"] = df["data"].dt.month
    df["dia_ano"] = df["data"].dt.dayofyear
    df["lag_7"] = df["quantidade_vendida"].shift(7)
    df["media_7"] = df["quantidade_vendida"].shift(1).rolling(7).mean()
    return df.dropna().reset_index(drop=True)


def criar_previsao(serie):
    """Avalia um modelo no trecho final do histórico e prevê os próximos sete dias."""
    preparado = preparar_features(serie)
    colunas = ["dia_semana", "mes", "dia_ano", "lag_7", "media_7"]
    if len(preparado) < 45:
        return None, None, "Histórico insuficiente para uma avaliação confiável."

    corte = max(int(len(preparado) * 0.85), len(preparado) - 60)
    corte = min(corte, len(preparado) - 14)
    treino = preparado.iloc[:corte]
    teste = preparado.iloc[corte:]

    modelo = RandomForestRegressor(
        n_estimators=100, max_depth=8, min_samples_leaf=3, random_state=42, n_jobs=-1
    )
    modelo.fit(treino[colunas], treino["quantidade_vendida"])
    pred_teste = np.maximum(0, modelo.predict(teste[colunas]))
    mae = mean_absolute_error(teste["quantidade_vendida"], pred_teste)
    rmse = np.sqrt(mean_squared_error(teste["quantidade_vendida"], pred_teste))

    historico = serie.sort_values("data").copy()
    valores = historico["quantidade_vendida"].astype(float).tolist()
    ultima_data = pd.to_datetime(historico["data"].max())
    previsoes = []

    for passo in range(1, 8):
        data_futura = ultima_data + pd.Timedelta(days=passo)
        lag7 = valores[-7] if len(valores) >= 7 else float(np.mean(valores))
        media7 = float(np.mean(valores[-7:])) if valores else 0.0
        linha = pd.DataFrame([{
            "dia_semana": data_futura.dayofweek,
            "mes": data_futura.month,
            "dia_ano": data_futura.dayofyear,
            "lag_7": lag7,
            "media_7": media7,
        }])
        estimativa = max(0, float(modelo.predict(linha[colunas])[0]))
        previsoes.append({"data": data_futura, "demanda_estimada": round(estimativa, 1)})
        valores.append(estimativa)

    previsoes_df = pd.DataFrame(previsoes)
    metricas = {"MAE": mae, "RMSE": rmse}
    teste_df = teste[["data", "quantidade_vendida"]].copy()
    teste_df["previsao"] = pred_teste
    return previsoes_df, (metricas, teste_df), None


verificar_login()

df = gerar_dados()
estoque_atual_df = carregar_estoque(df)

with st.sidebar:
    st.caption(f"Conectado como: {st.session_state.get('usuario', 'usuário')}")
    if st.button("Sair", use_container_width=True):
        st.session_state.autenticado = False
        st.session_state.pop("usuario", None)
        st.rerun()
    st.divider()
    pagina = st.radio("Navegação", ["Painel de análise", "Gerenciar produtos"], key="pagina_navegacao")

if pagina == "Gerenciar produtos":
    st.title("📦 Gerenciar produtos")
    st.caption("Cadastre produtos e altere preço, categoria e estoque. Os dados são salvos no armazenamento configurado.")

    with st.expander("➕ Cadastrar novo produto", expanded=True):
        with st.form("novo_produto_form", clear_on_submit=True):
            novo_nome = st.text_input("Nome do produto")
            categoria_personalizada = st.text_input("Categoria", value="Mercearia", help="Você pode usar uma categoria existente ou criar outra.")
            novo_preco = st.number_input("Preço unitário (R$)", min_value=0.01, value=1.00, step=0.50, format="%.2f")
            novo_estoque = st.number_input("Quantidade inicial em estoque", min_value=0, value=0, step=1)
            novo_minimo = st.number_input("Estoque mínimo", min_value=0, value=5, step=1)
            cadastrar = st.form_submit_button("Cadastrar produto", type="primary")
        if cadastrar:
            nome_normalizado = novo_nome.strip()
            if not nome_normalizado:
                st.error("Informe o nome do produto.")
            elif not str(categoria_personalizada).strip():
                st.error("Informe uma categoria válida.")
            elif estoque_atual_df["produto"].astype(str).str.casefold().eq(nome_normalizado.casefold()).any():
                st.error("Já existe um produto com esse nome.")
            else:
                nova_linha = pd.DataFrame([{
                    "produto": nome_normalizado,
                    "categoria": str(categoria_personalizada).strip(),
                    "preco_unitario": round(float(novo_preco), 2),
                    "estoque_atual": int(novo_estoque),
                    "estoque_minimo": int(novo_minimo),
                }])
                estoque_atual_df = pd.concat([estoque_atual_df, nova_linha], ignore_index=True)
                salvar_estoque(estoque_atual_df)
                st.success(f"Produto '{nome_normalizado}' cadastrado.")
                st.rerun()

    st.subheader("Editar produto existente")
    if estoque_atual_df.empty:
        st.info("Ainda não há produtos cadastrados.")
    else:
        produto_editar = st.selectbox("Selecione o produto", sorted(estoque_atual_df["produto"].tolist()), key="produto_editar")
        registro = estoque_atual_df.loc[estoque_atual_df["produto"] == produto_editar].iloc[0]
        with st.form("editar_produto_form"):
            editar_categoria = st.text_input("Categoria", value=str(registro["categoria"]))
            editar_preco = st.number_input("Preço unitário (R$)", min_value=0.01, value=max(0.01, float(registro["preco_unitario"])), step=0.50, format="%.2f")
            editar_estoque = st.number_input("Estoque atual", min_value=0, value=int(registro["estoque_atual"]), step=1)
            editar_minimo = st.number_input("Estoque mínimo", min_value=0, value=int(registro["estoque_minimo"]), step=1)
            salvar_edicao = st.form_submit_button("Salvar alterações", type="primary")
        if salvar_edicao:
            if not editar_categoria.strip():
                st.error("A categoria não pode ficar vazia.")
            else:
                idx_editar = estoque_atual_df.index[estoque_atual_df["produto"] == produto_editar][0]
                estoque_atual_df.at[idx_editar, "categoria"] = editar_categoria.strip()
                estoque_atual_df.at[idx_editar, "preco_unitario"] = round(float(editar_preco), 2)
                estoque_atual_df.at[idx_editar, "estoque_atual"] = int(editar_estoque)
                estoque_atual_df.at[idx_editar, "estoque_minimo"] = int(editar_minimo)
                salvar_estoque(estoque_atual_df)
                st.success(f"Dados de '{produto_editar}' atualizados.")
                st.rerun()

    st.subheader("Catálogo cadastrado")
    tabela_produtos = estoque_atual_df.rename(columns={
        "produto": "Produto", "categoria": "Categoria", "preco_unitario": "Preço (R$)",
        "estoque_atual": "Estoque atual", "estoque_minimo": "Estoque mínimo"
    }).copy()
    tabela_produtos["Preço (R$)"] = tabela_produtos["Preço (R$)"].map(lambda valor: dinheiro(float(valor)))
    st.dataframe(tabela_produtos, use_container_width=True, hide_index=True)
    st.info("O catálogo e o estoque podem ser compartilhados online quando o Supabase estiver configurado. O histórico sintético de vendas não é alterado pelo cadastro de produtos.")
    st.stop()

st.title("🛒 Mercadinho Boa Compra")
st.caption("Painel de análise de vendas, estoque e previsão de demanda")
st.info("**Protótipo acadêmico:** as vendas, os estoques e as leituras de IoT são dados sintéticos simulados, não registros reais de um comércio.")

with st.sidebar:
    st.header("Filtros")
    categorias = ["Todas"] + sorted(df["categoria"].unique().tolist())
    categoria_escolhida = st.selectbox("Categoria", categorias)
    produtos_disponiveis = df["produto"].unique().tolist()
    if categoria_escolhida != "Todas":
        produtos_disponiveis = df.loc[df["categoria"] == categoria_escolhida, "produto"].unique().tolist()
    produto_escolhido = st.selectbox("Produto para análise e previsão", sorted(produtos_disponiveis))
    data_min = df["data"].min().date()
    data_max = df["data"].max().date()
    periodo = st.date_input("Período de análise", value=(data_min, data_max),
                            min_value=data_min, max_value=data_max)
    st.divider()
    st.caption("Dados demonstrativos gerados automaticamente. Nenhum sensor físico está conectado.")

if isinstance(periodo, (tuple, list)) and len(periodo) == 2:
    inicio, fim = pd.Timestamp(periodo[0]), pd.Timestamp(periodo[1])
else:
    inicio, fim = pd.Timestamp(data_min), pd.Timestamp(data_max)

filtrado = df[(df["data"] >= inicio) & (df["data"] <= fim)].copy()
if categoria_escolhida != "Todas":
    filtrado = filtrado[filtrado["categoria"] == categoria_escolhida]

if filtrado.empty:
    st.warning("Não existem registros para os filtros selecionados.")
    st.stop()

vendas_por_produto = filtrado.groupby("produto")["quantidade_vendida"].sum()
mais_vendido = vendas_por_produto.idxmax() if len(vendas_por_produto) else "—"
estoque_baixo = int((estoque_atual_df["estoque_atual"] <= estoque_atual_df["estoque_minimo"]).sum())

faturamento_total = filtrado["faturamento"].sum()
unidades_total = int(filtrado["quantidade_vendida"].sum())
demanda_selecionada = df[df["produto"] == produto_escolhido].sort_values("data")
previsoes, resultado_modelo, erro_modelo = criar_previsao(demanda_selecionada)
demanda_futura = float(previsoes["demanda_estimada"].sum()) if previsoes is not None else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Faturamento no período", dinheiro(faturamento_total))
m2.metric("Unidades vendidas", f"{unidades_total:,}".replace(",", "."))
m3.metric("Produto mais vendido", mais_vendido)
m4.metric("Produtos com estoque baixo", estoque_baixo)

st.subheader("Visão geral das vendas")
c1, c2 = st.columns(2)
with c1:
    vendas_tempo = filtrado.groupby("data", as_index=False)["faturamento"].sum()
    fig = px.line(vendas_tempo, x="data", y="faturamento", title="Faturamento ao longo do tempo",
                  labels={"data": "Data", "faturamento": "Faturamento (R$)"})
    fig.update_layout(margin=dict(l=10, r=10, t=55, b=10))
    st.plotly_chart(fig, use_container_width=True)
with c2:
    ranking = filtrado.groupby("produto", as_index=False)["quantidade_vendida"].sum()
    ranking = ranking.sort_values("quantidade_vendida", ascending=False).head(10)
    fig = px.bar(ranking, x="quantidade_vendida", y="produto", orientation="h",
                 title="10 produtos mais vendidos", labels={"quantidade_vendida": "Unidades", "produto": "Produto"})
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, margin=dict(l=10, r=10, t=55, b=10))
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Gerenciar estoque")
st.caption("Registre entradas e saídas de mercadorias. As alterações são salvas no armazenamento configurado e permanecem disponíveis após reabrir a aplicação.")
with st.form("form_movimentacao_estoque", clear_on_submit=True):
    col_produto, col_operacao, col_quantidade = st.columns([2, 1, 1])
    with col_produto:
        produto_movimentacao = st.selectbox("Produto", sorted(estoque_atual_df["produto"].tolist()), key="produto_movimentacao")
    with col_operacao:
        operacao = st.selectbox("Movimentação", ["Entrada de mercadoria", "Saída de mercadoria", "Ajuste de estoque"], key="operacao_estoque")
    with col_quantidade:
        quantidade_movimentacao = st.number_input("Quantidade (unidades)", min_value=0, step=1, value=1, key="quantidade_estoque")
    st.caption("Exemplo: se chegaram 20 pacotes de arroz, selecione Arroz 5 kg, Entrada de mercadoria e quantidade 20.")
    salvar_movimentacao = st.form_submit_button("Salvar movimentação", type="primary")

if salvar_movimentacao:
    linha_produto = estoque_atual_df.index[estoque_atual_df["produto"] == produto_movimentacao]
    if len(linha_produto) == 0:
        st.error("Produto não encontrado no estoque.")
    elif quantidade_movimentacao <= 0:
        st.error("Informe uma quantidade maior que zero.")
    else:
        idx = linha_produto[0]
        estoque_anterior = int(estoque_atual_df.at[idx, "estoque_atual"])
        if operacao == "Entrada de mercadoria":
            novo_estoque = estoque_anterior + int(quantidade_movimentacao)
        elif operacao == "Saída de mercadoria":
            novo_estoque = estoque_anterior - int(quantidade_movimentacao)
            if novo_estoque < 0:
                st.error(f"Estoque insuficiente. Quantidade disponível: {estoque_anterior}.")
                st.stop()
        else:
            novo_estoque = int(quantidade_movimentacao)
        estoque_atual_df.at[idx, "estoque_atual"] = novo_estoque
        salvar_estoque(estoque_atual_df)
        st.success(f"Estoque de {produto_movimentacao} atualizado: {estoque_anterior} → {novo_estoque} unidades.")
        st.rerun()

st.subheader("Estoque e reposição")
estoque_visivel = estoque_atual_df.copy()
if categoria_escolhida != "Todas":
    estoque_visivel = estoque_visivel[estoque_visivel["categoria"] == categoria_escolhida]
estoque_visivel["status"] = np.where(
    estoque_visivel["estoque_atual"] <= estoque_visivel["estoque_minimo"], "Estoque crítico",
    np.where(estoque_visivel["estoque_atual"] <= estoque_visivel["estoque_minimo"] * 1.5, "Atenção", "Adequado")
)
estoque_visivel["sugestao_reposicao"] = np.maximum(
    0, estoque_visivel["estoque_minimo"] * 2 - estoque_visivel["estoque_atual"]
).astype(int)
fig = px.bar(estoque_visivel.sort_values("estoque_atual", ascending=False),
             x="produto", y="estoque_atual", color="status",
             title="Estoque atual por produto",
             labels={"produto": "Produto", "estoque_atual": "Unidades em estoque", "status": "Situação"})
fig.update_layout(xaxis_tickangle=-35, margin=dict(l=10, r=10, t=55, b=10))
st.plotly_chart(fig, use_container_width=True)
st.dataframe(
    estoque_visivel[["produto", "categoria", "estoque_atual", "estoque_minimo", "status", "sugestao_reposicao"]]
    .rename(columns={"produto": "Produto", "categoria": "Categoria", "estoque_atual": "Estoque atual",
                     "estoque_minimo": "Estoque mínimo", "status": "Situação",
                     "sugestao_reposicao": "Sugestão de reposição (un.)"}),
    use_container_width=True, hide_index=True
)
st.caption("A sugestão de reposição é uma regra demonstrativa baseada no estoque mínimo; não representa uma ordem de compra.")

st.subheader(f"Previsão de demanda: {produto_escolhido}")
if erro_modelo:
    st.warning(erro_modelo)
else:
    metricas, teste_df = resultado_modelo
    p1, p2, p3 = st.columns(3)
    p1.metric("Demanda estimada — próximos 7 dias", f"{demanda_futura:.1f} un.")
    p2.metric("MAE no período de teste", f"{metricas['MAE']:.2f} un.")
    p3.metric("RMSE no período de teste", f"{metricas['RMSE']:.2f} un.")

    comparacao = teste_df.melt(id_vars="data", value_vars=["quantidade_vendida", "previsao"],
                               var_name="tipo", value_name="unidades")
    comparacao["tipo"] = comparacao["tipo"].map({
        "quantidade_vendida": "Venda observada (teste)", "previsao": "Previsão do modelo"
    })
    fig = px.line(comparacao, x="data", y="unidades", color="tipo",
                  title="Vendas observadas x previsões no período de teste",
                  labels={"data": "Data", "unidades": "Unidades", "tipo": "Série"})
    st.plotly_chart(fig, use_container_width=True)

    fig = px.bar(previsoes, x="data", y="demanda_estimada",
                 title="Estimativa para os próximos sete dias",
                 labels={"data": "Data futura", "demanda_estimada": "Unidades estimadas"})
    st.plotly_chart(fig, use_container_width=True)
    st.caption("O modelo Random Forest é treinado com o histórico anterior e avaliado em um trecho posterior. MAE e RMSE medem erros no conjunto de teste; previsões são estimativas, não garantias.")

st.subheader("Demonstração conceitual de IoT")
produto_iot = df[df["produto"] == produto_escolhido].sort_values("data").tail(30)
ultima = produto_iot.iloc[-1]
i1, i2, i3 = st.columns(3)
i1.metric("Última leitura simulada", f"{ultima['leitura_iot_simulada']:.1f} un.")
estoque_produto_atual = estoque_atual_df.loc[estoque_atual_df["produto"] == produto_escolhido].iloc[0]
i2.metric("Estoque atual registrado", f"{int(estoque_produto_atual['estoque_atual'])} un.")
i3.metric("Limite mínimo", f"{int(estoque_produto_atual['estoque_minimo'])} un.")
fig = px.line(produto_iot, x="data", y="leitura_iot_simulada",
              title="Histórico de leituras simuladas do sensor",
              labels={"data": "Data", "leitura_iot_simulada": "Leitura estimada (unidades)"})
st.plotly_chart(fig, use_container_width=True)
st.warning("O histórico de leituras é simulado e não vem de sensor físico. O estoque atual exibido ao lado é o valor salvo pelo usuário.")

st.subheader("Consultar e exportar dados")
with st.expander("Visualizar registros filtrados"):
    st.dataframe(filtrado.sort_values("data", ascending=False), use_container_width=True, hide_index=True)
    csv = filtrado.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Baixar dados filtrados em CSV", data=csv,
                       file_name="mercadinho_dados_filtrados.csv", mime="text/csv")

st.caption("Mercadinho Boa Compra | Protótipo acadêmico de análise de dados, aprendizagem de máquina e simulação de IoT.")
