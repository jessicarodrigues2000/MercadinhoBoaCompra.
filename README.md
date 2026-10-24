# Mercadinho Boa Compra — versão com login e catálogo editável

Protótipo acadêmico de análise de vendas e estoque, previsão de demanda e demonstração conceitual de IoT. O histórico inicial de vendas e as leituras de IoT são sintéticos/simulados.

## Novidades desta versão
- Tela de login com usuários definidos nos Secrets.
- Menu de navegação entre painel e gerenciamento de produtos.
- Cadastro de novos produtos com categoria, preço e estoque inicial.
- Edição de categoria, preço, estoque atual e estoque mínimo.
- Persistência local em CSV para testes no computador.
- Integração opcional com Supabase para compartilhar o catálogo e estoque entre integrantes quando a aplicação estiver online.

## 1. Preparar o projeto local
1. Extraia a pasta ZIP.
2. Dentro da pasta do projeto, copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml`.
3. Abra `secrets.toml` e substitua todas as senhas de exemplo por senhas exclusivas para o trabalho. Não reutilize senhas pessoais.
4. Abra a pasta no VS Code e use Terminal → Novo Terminal.
5. Execute um comando por vez:

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Se `py` não funcionar, tente `python -m venv .venv`. Se a ativação falhar no PowerShell, use o terminal CMD e execute `.venv\Scripts\activate.bat`.

## 2. Teste local
Sem configuração do Supabase, os dados do catálogo/estoque são gravados em `estoque_atual.csv` ao lado do `app.py`. Esse arquivo local não é compartilhado com outros computadores.

Teste: entrar com uma das contas configuradas; abrir **Gerenciar produtos**; cadastrar um produto; alterar o preço ou o estoque; sair e entrar novamente; confirmar que as alterações permanecem.

## 3. Compartilhar dados online (Supabase)
1. Crie um projeto no Supabase.
2. Abra **SQL Editor**, cole o conteúdo de `supabase_schema.sql` e execute.
3. Nas configurações/API do projeto, copie a URL do projeto e a chave `service_role` (não a chave anon). Trate a chave `service_role` como senha administrativa.
4. Para teste local, preencha a seção `[supabase]` em `.streamlit/secrets.toml`.
5. Publique o app no Streamlit Community Cloud a partir de um repositório Git privado ou adequado para o trabalho. Nas configurações do app publicado, em **Settings → Secrets**, copie o conteúdo das configurações, incluindo `[users]` e `[supabase]`.
6. Não envie o arquivo `secrets.toml` para o Git nem inclua a chave no ZIP.

Com o Supabase configurado, os produtos e estoques ficam no banco compartilhado. O histórico de vendas e os dados usados no modelo continuam sendo sintéticos e gerados pela aplicação; cadastrar um produto não cria automaticamente histórico de vendas para ele.

## Limitações e segurança
- Login simplificado para demonstração acadêmica; não é um sistema de autenticação corporativo. Não use senhas pessoais ou dados reais sensíveis.
- A aplicação usa a chave `service_role` somente no servidor Streamlit. Nunca a exponha em código público ou navegador.
- O Supabase permite compartilhar catálogo/estoque; o arquivo CSV local não sincroniza entre computadores.
- A previsão é experimental e baseada em dados sintéticos; não representa previsão validada para um comércio real.
- O cadastro e a edição de produtos não alteram retroativamente o histórico sintético de vendas.
