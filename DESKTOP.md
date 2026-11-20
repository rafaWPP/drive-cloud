# Drive Cloud — início do aplicativo instalável

Esta branch adiciona a base do aplicativo Linux usando **Tauri 2**, reaproveitando o frontend React/Vite existente. Nenhum dado, sessão do Telegram ou banco SQLite é alterado por esta etapa.

## Primeira versão: limitação importante

**Este empacotamento ainda não inclui o backend Python/Telethon.** A janela desktop abre o frontend, mas os recursos que chamam `/api` só funcionarão com o backend de desenvolvimento ativo. Não distribuir este pacote como produto final e não afirmar que login, upload e download funcionam sem serviço local.

A meta da próxima etapa é incluir um processo local integrado/sidecar ao instalador com inicialização e encerramento automáticos e armazenamento seguro das sessões. Isso **não** significa instalar um servidor em nuvem da empresa, apenas encapsular o serviço local atual; uma migração posterior para integração nativa também poderá ser avaliada.

## Compilar no Linux

Requisitos: Node.js 22, Rust, bibliotecas de desenvolvimento do Tauri 2/WebKitGTK 4.1.

```bash
sudo apt-get update
sudo apt-get install -y libwebkit2gtk-4.1-dev build-essential curl wget file libxdo-dev libssl-dev librsvg2-dev libayatana-appindicator3-dev
npm install
npx tauri icon public/drive-cloud-logo.svg
npm run tauri:dev
# ou gerar o instalador:
npm run tauri:build
```

Arquivo esperado: `src-tauri/target/release/bundle/deb/*.deb`.

Também é possível abrir a aba **Actions** do GitHub e executar **Linux Desktop (Tauri)**. Se o workflow passar, o arquivo `.deb` fica disponível como artefato da execução.

## Próximas etapas antes de testar o produto completo

1. Empacotar a integração Telegram local no aplicativo, sem exigir Python ou terminal do usuário.
2. Corrigir a comunicação `/api` com o processo local no WebView, incluindo restrições de acesso e segurança da sessão.
3. Persistir e recuperar metadados do catálogo também no Telegram para sincronização entre dispositivos.
4. Testar login, upload, download, prévias, desconexão e atualizações; depois preparar Windows e Android.
5. Validar limites, termos e riscos de uso comercial da API Telegram.

Nunca publicar `backend/.env`, `backend/.data`, arquivos `.session` ou credenciais no repositório.
