---
description: Ensina o copiloto sobre o seu negócio (ofertas, preços, cliente, objeções, script de vendas). Usado em todas as reuniões.
argument-hint: "[opcional: caminho de um arquivo com o seu script de vendas ou material]"
---

Ative a skill `copiloto-reuniao`. `COP` = `python "${CLAUDE_PLUGIN_ROOT}/motor/copiloto.py"` (Mac/Linux: `python3`).

Objetivo: montar (ou atualizar) o perfil do usuário em `~/CopilotoReuniao/perfil/`. Rode `COP perfil` para ver a pasta e o que já existe.

1. **Se já existe um perfil**, mostre um resumo de 5 linhas e pergunte o que mudou (oferta nova, preço novo, script novo). Atualize só isso.

2. **Material pronto primeiro (poupa perguntas).** Pergunte numa mensagem só:
   "Você já tem algo escrito sobre o seu negócio? Pode ser script de vendas, página de vendas, proposta, apresentação ou anotações. Cole o texto aqui ou me diga onde está o arquivo (Word, PDF, Google Docs exportado, txt). Se não tiver, tudo bem: eu te faço umas perguntas."
   - Se vier arquivo (ou `$ARGUMENTS` tiver um caminho), leia com as ferramentas que você tiver (Read para txt/md/pdf; para .docx use a skill de documentos se existir, ou peça para colar o texto).
   - Se tiver um **script de vendas**, salve-o organizado em `perfil/script-de-vendas.md`: as etapas, as perguntas e as frases-chave, preservando o jeito do usuário. Não reescreva no seu estilo.

3. **Entrevista curta** só para o que faltar. Faça em blocos de 2 ou 3 perguntas por mensagem, aceite respostas soltas e não insista no que a pessoa pular:
   - **Ofertas:** o que você vende? Para quem? Quanto custa e como dá para pagar? Tem garantia?
   - **Cliente:** quem é o cliente ideal? O que ele mais reclama, com as palavras dele? Quem costuma decidir junto?
   - **Objeções:** quais objeções você mais ouve? Como você costuma responder cada uma?
   - **Provas:** algum caso com número, depoimento ou diferencial que você gosta de citar?
   - **Condução:** você usa um roteiro na call? Faz mentoria? Como conduz as sessões?
   - **Nunca:** tem algo que você nunca promete, ou palavras que não usa?
   - **Nomes:** quais nomes de produtos, métodos e termos a transcrição precisa escrever certo?

4. **Escreva `perfil/perfil.md`** seguindo `${CLAUDE_PLUGIN_ROOT}/skills/copiloto-reuniao/perfil-modelo.md`.
   - Use as palavras do próprio usuário.
   - O que ele não informou fica como "(não informado)". Não invente preço, garantia nem resultado.
   - Preencha a seção "Nomes e termos" (o motor usa essa lista para a transcrição acertar os nomes).
   - Se o usuário der um nome para aparecer no painel, rode `COP config rotulo_voce "<NOME EM MAIÚSCULAS>"`.

5. Mostre um resumo do perfil em até 10 linhas e diga que ele já vale a partir da próxima `/reuniao`. Para mudar depois: `/reuniao-perfil`.
