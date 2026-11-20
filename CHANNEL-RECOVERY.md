# Recuperação após exclusão do canal Telegram — Drive Cloud 0.1.15

Esta recuperação só aparece quando a **conta Telegram está conectada** mas o canal de armazenamento anteriormente vinculado não existe mais ou não está acessível nessa conta.

## Comportamento

1. O Drive Cloud mantém a etapa **Canal privado** aberta, mostra o erro original e procura novamente o canal registrado.
2. Aparece uma seção **Recuperar armazenamento** com as opções:
   - Se houver outro canal privado **Drive Cloud Storage** pertencente à conta, pode **reutilizar o canal encontrado**.
   - Se não houver outro canal compatível, pode **Criar novo canal privado**, após marcar a caixa de confirmação.
3. O aplicativo verifica novamente a conta e o canal anterior **antes de realizar a ação**; um vínculo alterado ou um canal novamente acessível bloqueia a operação.
4. Caso seja necessário criar um canal, o Telegram recebe uma única solicitação. No próximo teste, o Drive Cloud tenta localizar o canal criado antes de criar outro.
5. A foto com a **logo do Drive Cloud** é aplicada se o canal não tiver foto e a conta for proprietária.
6. Depois de confirmar o vínculo novo, o onboarding prossegue automaticamente ao Meu Drive.

## Segurança de dados

**Criar um novo canal não recupera arquivos excluídos junto com o antigo**. Os IDs de mensagens Telegram pertencem ao canal anterior e não servem para baixar arquivos de outro canal.

Para não misturar esses IDs, o catálogo anterior permanece no mesmo banco SQLite do aparelho, mas recebe um identificador local de arquivo histórico. Pastas sincronizadas, snapshots e links antigos também deixam de pertencer à conta ativa, para impedir envios ou downloads no canal errado. Nenhum registro do catálogo anterior é apagado; o histórico não é exibido automaticamente no novo Drive.

A confirmação é obrigatória e há avisos com a contagem de entradas antigas. Se houver canais candidatos, o Drive Cloud **não cria duplicados**: primeiro exige a seleção de um canal existente.

## Teste sugerido (somente com dados descartáveis)

1. Login Telegram com canal privado de teste e upload de arquivo descartável.
2. Excluir **o canal inteiro** diretamente no Telegram.
3. Voltar ao Drive Cloud: confirmar erro de canal indisponível.
4. Marcar o aviso e clicar em **Criar novo canal privado**.
5. Verificar que o novo canal é privado, tem logo, e o Drive aparece vazio, sem referências quebradas do canal antigo.
6. Fechar e reabrir o aplicativo: o novo canal deve ser reutilizado, sem criar outro.
7. Repetir após criar outro canal de mesmo nome previamente: deve aparecer **Usar canal existente** em vez de criar mais um.

**Não usar este procedimento com seu único backup de arquivos importantes**. A exclusão de um canal pode ser irreversível; não há restauração automática de mensagens eliminadas do Telegram.
