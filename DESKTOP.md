# Drive Cloud — aplicativo Linux experimental (Tauri 2)

O build do GitHub Actions agora tenta gerar um **.deb incluindo a interface React e o conector Telegram Python em um executável local** (PyInstaller). O cliente não precisa instalar Python para iniciar esse conector. O código atual ainda não foi validado por um teste de instalação ponta a ponta.

## Instalar para teste

1. Acesse **Actions > Linux Desktop (Tauri)** nesta branch.
2. Quando houver execução bem-sucedida, baixe o artefato `drive-cloud-linux-deb-experimental`, extraia o ZIP e instale o `.deb`.
3. Para testar login, a conta precisa de credenciais de API MTProto. Como **não colocamos segredos no GitHub**, configure localmente `~/.local/share/br.com.drivecloud.app/.env` (caminho a confirmar com o app instalado e versão de Tauri) contendo:
   ```dotenv
   TELEGRAM_API_ID=seu_id
   TELEGRAM_API_HASH=seu_hash
   ```
   O caminho efetivo usado pelo app é o diretório retornado por `app_local_data_dir()`. Reinicie o aplicativo depois de configurar.
4. **Não** envie a pasta de dados, arquivos `.session` nem `.env` ao GitHub.

> O login ainda exige configuração manual no piloto. Antes de distribuir comercialmente, é necessário resolver a configuração do ID/hash do aplicativo MTProto, proteger a API local contra outras aplicações na máquina, criar testes e validar o empacotamento.

## Desenvolvimento

- `npm install`
- `npm run dev` e backend Python normal continuam disponíveis sem Tauri.
- `npm run tauri:dev` exige primeiro gerar o binário sidecar `src-tauri/binaries/drive-cloud-backend-<target-triple>` com PyInstaller, assim como o workflow.
- `npm run tauri:build` gera o pacote `.deb` se todas as dependências estiverem instaladas.

## Dados e compatibilidade

O sidecar usa uma pasta própria de dados persistentes via `DRIVE_CLOUD_DATA_DIR`, definida pelo aplicativo. **Os dados antigos em `backend/.data` não são migrados automaticamente.** Nunca apague ou substitua essa pasta sem antes fazer uma cópia segura; ela contém a sessão Telegram e catálogo SQLite com a estrutura de pastas.

Os arquivos continuam armazenados no canal Telegram; a organização do Drive ainda depende de SQLite local, e a sincronização entre dispositivos **não está pronta**. Links `localhost` não funcionam como compartilhamento público.

## Próximos testes obrigatórios

- Validar compilação e instalação `.deb` real em distribuição Linux compatível.
- Garantir que o lado Tauri consegue requisitar a API local, inclusive CORS e prévias.
- Validar login/QR, transferências, arquivos locais, reinicialização, permissões e encerramento.
- Criar onboarding de credenciais e gestão segura de sessões, controlar acesso à porta local.
- Sincronizar catálogo/pastas entre dispositivos pelo Telegram.
- Preparar Windows e Android com arquiteturas nativas apropriadas.

Sem hospedagem própria para arquivos, o produto continua dependendo dos termos e limites do Telegram.
