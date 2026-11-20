# Conexão inicial do Drive Cloud — 0.1.10

O Drive Cloud só abre a navegação de arquivos quando o backend confirma a conta Telegram **e** o canal privado de armazenamento.

## Sequência de início

1. Sem API ID/API Hash: exibir os dois campos no onboarding. O botão de criação abre `https://my.telegram.org/apps` no navegador oficial. As credenciais são guardadas somente no diretório local do aplicativo.
2. Com credenciais e sem sessão: exibir as opções de conexão por QR Code e telefone, incluindo confirmação do código e senha 2FA quando necessário.
3. Com conta autorizada, mas sem canal: o Drive Cloud **busca e reutiliza** o canal privado vinculado, ou cria o canal automaticamente se não existir. O canal não deve ser duplicado se um vínculo registrado estiver inacessível.
4. Após criar ou reencontrar um canal próprio que **ainda não tenha foto**, a integração tenta definir como avatar a **logo original do Drive Cloud**, convertida para JPEG quadrado. A imagem é embutida no backend para continuar disponível em instaladores Linux/Windows sem depender dos arquivos do frontend. Uma foto personalizada existente **nunca é substituída**.
5. Se a edição da foto falhar, o canal e a conta continuam utilizáveis; apenas a identidade visual fica pendente. Se o vínculo Telegram/canal falhar, o Drive não é aberto.
6. O onboarding avança para o Drive automaticamente quando a verificação do canal retornar `ready=true`. Ao desconectar ou sair da sessão, o Drive volta a ser bloqueado e o onboarding reaparece.

## Testes

- Primeira instalação, sem API ID e Hash: etapa 1.
- Credenciais válidas, sem Telegram conectado: etapa 2.
- QR Code / número de telefone e segunda etapa: etapa 3.
- Conta já configurada e canal privado existente: abre Drive sem onboarding e não cria outro canal.
- Canal próprio sem foto: a foto deve ser a mesma logo do Drive Cloud.
- Canal com foto personalizada: preserva a imagem anterior.
- Telegram recusa mudança de foto: onboarding não deve ficar bloqueado por causa da imagem.
- Falha no conector local: tela de erro com opção de tentar novamente, sem mostrar arquivos antes da confirmação.
- Testes visuais nas resoluções desktop e mobile, sem tela cortada.

O canal é privado e pertence à conta Telegram autorizada. **Não solicita ao usuário que forneça o canal manualmente.** Usar dados de teste ao validar o fluxo novo.
