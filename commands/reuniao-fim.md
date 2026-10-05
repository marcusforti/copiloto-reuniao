---
description: Encerra a reunião e gera o resumo com tarefas, objeções, métricas e follow-up pronto
argument-hint: "[opcional: pasta da sessão]"
---

Ative a skill `copiloto-reuniao`. `COP` = `python "${CLAUDE_PLUGIN_ROOT}/motor/copiloto.py"` (Mac/Linux: `python3`).

1. Pare o Monitor da reunião, se estiver armado.
2. Rode `COP parar $ARGUMENTS` (se já estiver parado, tudo bem) e depois `COP transcricao $ARGUMENTS`. Leia o arquivo `TRANSCRICAO=` **inteiro** com a ferramenta Read e o `briefing.json` da mesma pasta.
3. Escreva `<SESSAO>/resumo-dados.json` no formato da skill:
   - Seja específico. Use os números, nomes e frases do cliente.
   - Próximos passos com dono e prazo.
   - Objeções com status honesto.
   - Follow-up de WhatsApp curto, humano, no tom de quem conduziu a call, retomando o próximo passo combinado.
   - Coach: 2 ou 3 coisas que funcionaram e 2 ou 3 para melhorar, citando momentos reais da conversa.
   - Sem dados sensíveis. A transcrição pode ter errado nomes e números: na dúvida, marque "(confirmar)".
4. Rode `COP resumo --sessao "<SESSAO>" --dados "<SESSAO>/resumo-dados.json"`. Ele abre o `resumo.html` no navegador.
5. No chat, mostre só o essencial:
   - 3 linhas de resumo.
   - Os próximos passos.
   - A mensagem de follow-up pronta para copiar.
   - O caminho do `resumo.html`.
