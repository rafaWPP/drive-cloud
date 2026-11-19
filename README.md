# Drive Cloud — versão local

Drive pessoal para testes em localhost, usando React + Vite, modo grade/lista, pastas, upload, download, favoritos, pesquisa e lixeira.

## Como rodar no Linux

Instale o Node.js (versão 20.19+ ou 22.12+), depois:

```bash
git clone https://github.com/rafaWPP/drive-cloud.git
cd drive-cloud
npm install
npm run dev
```

Abra http://localhost:5173

**IMPORTANTE:** esta versão **não** conecta ao Telegram. Arquivos enviados são guardados somente no IndexedDB do navegador utilizado, não em uma pasta de backups do Linux. Limpar dados do site, trocar navegador/perfil ou perder o computador pode excluir os arquivos. Não use para backups importantes.

O projeto é uma V1 visual e funcional para avaliação do layout.
