---
description: Mostra o copiloto funcionando numa venda simulada (sem microfone, sem cliente)
---

`COP` = `python "${CLAUDE_PLUGIN_ROOT}/motor/copiloto.py"` (Mac/Linux: `python3`).

1. Explique em uma linha: "Vou simular uma call de venda (clínica de estética, mentoria de R$ 4.900) para você ver o painel funcionando. Leva uns 2 minutos."
2. Rode em segundo plano: `COP simular "${CLAUDE_PLUGIN_ROOT}/exemplos/demo-venda.json"`. O painel abre sozinho no navegador.
3. Enquanto roda, explique o que olhar:
   - **FALE AGORA:** a próxima frase.
   - **Por quê:** o motivo, tirado do que o cliente disse.
   - **Perguntas:** dá para marcar as que você já fez.
   - **O que o cliente revelou:** dores, números e decisores.
   - **Objeções:** com a resposta pronta.
   - **Histórico:** os conselhos anteriores (← →).
   - **Medidores:** mostram se o copiloto está ouvindo os dois lados.
   - **📱:** abre no celular.
4. No fim, sugira `/reuniao-teste` e depois `/reuniao` na próxima call de verdade. Para ensaiar com áudio de verdade passando pela transcrição, existe `COP simular ... --audio`.
