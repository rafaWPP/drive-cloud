# Drive Cloud — versão local

Drive pessoal para testes no Linux usando React + Vite. Permite pastas, lista e grade, upload/download local, favoritos e pesquisa.

## 1. Frontend

Node.js versão 20.19+ ou 22.12+ recomendado.

```bash
git clone https://github.com/rafaWPP/drive-cloud.git
cd drive-cloud
npm install
npm run dev
```

Abra http://localhost:5173.

## 2. Conectar sua conta Telegram (local)

É preciso obter suas credenciais **api_id** e **api_hash** em https://my.telegram.org, na área API development tools. Essas credenciais são do seu aplicativo MTProto, não um bot token.

No terminal, na raiz do projeto:

```bash
cd backend
cp .env.example .env
nano .env
```

Preencha `TELEGRAM_API_ID` e `TELEGRAM_API_HASH`, sem aspas, salve e execute:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000
```

Deixe esse terminal aberto. Em outro terminal execute `npm run dev` na raiz do projeto. Na interface web, vá em **Configurações > Conexão Telegram**. Informe o telefone com DDI, o código recebido e sua senha de duas etapas, se pedida.

**Importante:** a primeira integração apenas faz login e guarda a sessão localmente. Uploads e downloads de arquivos ainda utilizam IndexedDB do navegador, **não** o Telegram. A conexão Telegram não sincroniza os arquivos nesta versão.

## Segurança

- Nunca envie seu `backend/.env`, a pasta `backend/.data` ou arquivos `*.session` ao GitHub nem compartilhe códigos de login.
- Proteja seu usuário Linux e use criptografia de disco: a sessão local concede acesso à conta Telegram.
- A API de teste escuta somente em `127.0.0.1:8000`, não deve ser exposta na internet.
- IndexedDB é armazenamento local do navegador e não substitui um sistema de backup. Limpar os dados do site pode apagar os arquivos.
- A opção **Desconectar backend** fecha a conexão do processo; **Sair do Telegram** revoga a sessão.

## Login com QR Code

Na tela **Configurações > Conexão Telegram**, escolha **Gerar QR Code**. No celular abra **Telegram > Configurações > Dispositivos > Conectar dispositivo** e escaneie. O código temporário pode expirar; nesse caso clique em **Gerar outro QR Code**. Caso sua conta exija senha de duas etapas, informe-a na tela do Drive. A alternativa de login por telefone continua disponível. Após atualizar o projeto, reinstale as dependências Python com `pip install -r requirements.txt` e reinicie o backend. O código QR é produzido localmente, sem serviço externo.

## Canal privado criado automaticamente

Ao concluir a autorização no Telegram, a tela **Configurações > Conexão Telegram** chama a API local para preparar o canal privado `Drive Cloud Storage`. Se não houver vínculo, o backend procura um canal próprio com esse nome e, quando não encontra, cria um canal privado (tipo broadcast) com a API Telegram. Salva o identificador em `backend/.data/storage_channels.json`, separado pelo ID da conta. Nas próximas conexões, reutiliza o mesmo canal. Se o canal associado sumir, o sistema **não cria outro automaticamente**: exibe um aviso para evitar duplicações.

A criação só acontece depois da autenticação e quando a tela de conexão é aberta. O programa **ainda não envia arquivos ao canal**: uploads continuam salvos no IndexedDB do navegador. Não apague `backend/.data` — é onde ficam os vínculos e a sessão Telegram. Esse diretório está ignorado no Git. Se fizer backup dessa pasta, trate-o como material confidencial.

Para atualizar o projeto, execute `git pull origin main`, reinicie o backend e recarregue a página. A criação de canal é uma operação real na sua conta Telegram e depende dos limites e permissões do Telegram.

## 3. Upload e download reais (Telegram Cloud V1)

Depois de conectar a conta e criar o canal privado, abra **Meu Drive > Nuvem Telegram**. Essa área é separada de **Arquivos locais**, que continua usando IndexedDB do navegador.

- **Enviar ao Telegram** faz upload real para o canal privado associado à conta.
- **Baixar** busca o conteúdo pelo identificador da mensagem no Telegram.
- **Nova pasta** registra pastas no SQLite local; não cria um canal para cada pasta.
- Os metadados ficam em `backend/.data/files.sqlite3`, o vínculo do canal em `backend/.data/storage_channels.json` e a sessão em `backend/.data/telegram.session`. Nenhum deles vai para o GitHub.
- Limite piloto: **20 MB por arquivo**. Não há envio em partes, fila resiliente, criptografia de ponta a ponta própria ou restauração entre máquinas nesta etapa.
- **Atenção**: arquivos que estavam em **Arquivos locais** não são migrados automaticamente para o Telegram. O canal do Telegram guarda o conteúdo, mas sem o banco SQLite local a listagem e a estrutura de pastas desta versão não são reconstruídas automaticamente.
- Faça backup seguro do diretório `backend/.data` (ele contém credenciais sensíveis!) e mantenha outra cópia dos arquivos importantes.

Atualização no Linux (nos dois terminais, com o backend parado enquanto instala dependências):

```bash
cd ~/Área\ de\ trabalho/drive-cloud
git pull origin main
cd backend
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000
```

No outro terminal, execute `npm run dev` na pasta raiz. Acesse `http://localhost:5173`.

O projeto é experimental; **não use o Telegram como única cópia de backup**.
