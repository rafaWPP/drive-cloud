# Conector Telegram (somente local)

**Não envie o arquivo .env, arquivos .session ou a pasta .data ao GitHub.**

1. Obtenha seu próprio api_id e api_hash em https://my.telegram.org (API development tools).
2. Na pasta `backend`, copie `.env.example` para `.env` e coloque os dados obtidos.
3. Inicie o backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000
```

4. Em outro terminal, execute `npm run dev` na raiz do projeto.
5. Abra http://localhost:5173, entre em Configurações > Conexão Telegram e faça login.

O conector aceita somente requisições locais e exige origem do frontend nas ações de escrita. A sessão local é sensível: mantenha permissões de usuário e criptografia de disco. A opção **Desconectar backend** não revoga a sessão, enquanto **Sair do Telegram** revoga a autorização.

**Limitação:** Esta etapa apenas autoriza a conta. Uploads do Drive ainda continuam no IndexedDB do navegador, sem transferência para o Telegram.
