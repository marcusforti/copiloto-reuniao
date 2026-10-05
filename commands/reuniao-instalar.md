---
description: Instala e configura o Copiloto de Reunião (modo grátis no PC ou modo pago por API)
---

`COP` = `python "${CLAUDE_PLUGIN_ROOT}/motor/copiloto.py"` (Mac/Linux: `python3`).

1. **Python 3.10+**: confira com `python --version` (Mac: `python3 --version`).
   - **Windows sem Python:** `winget install -e --id Python.Python.3.12`. Depois peça para fechar e abrir o terminal/Claude Code se o comando não for encontrado.
   - **Mac sem Python:** `brew install python@3.12` (sem Homebrew: https://brew.sh).

2. **Escolha do modo**. Pergunte ao usuário (AskUserQuestion), explicando curto:
   - **Grátis (recomendado para começar):** transcreve no próprio PC. Precisa de uns 2 GB de RAM livres. Nada sai do computador.
   - **Pago, transcrição Deepgram:** mais rápido e preciso, quase não pesa no PC. Conta nova ganha US$ 200 de crédito, que dá centenas de horas. Custa ~US$ 0,30 por hora por canal depois disso. Chave em https://console.deepgram.com
   - **Pago, transcrição Soniox:** o mais barato (~US$ 0,12/h por canal), sem crédito grátis. Chave em https://console.soniox.com
   - Opcional para quem quer independência total do Claude Code: **conselhos pela API da Anthropic** (`cerebro api`, usa ANTHROPIC_API_KEY, cobrado por uso).

3. Rode `COP instalar` (com `--api` se escolheu o cérebro por API). Na primeira vez leva alguns minutos (bibliotecas + modelo de transcrição).

4. Configure:
   - **Pago:** `COP config transcricao deepgram` (ou `soniox`) e `COP chave deepgram <CHAVE>`. **Nunca** repita a chave no chat depois de salvar.
   - **Cérebro por API:** `COP config cerebro api` e `COP chave anthropic <CHAVE>`.
   - **Sem fone de ouvido:** `COP config fone false`. Isso liga o filtro de eco.
   - **Nomes nos rótulos (opcional):** `COP config rotulo_voce "MARCUS"`.

5. **Mac:** rode `bash "${CLAUDE_PLUGIN_ROOT}/instalar/instalar-mac.sh"` para instalar o BlackHole e siga as instruções que ele mostrar (Multi-Output Device).

6. Rode o `/reuniao-teste`. Depois explique que é só digitar `/reuniao venda NomeDoCliente o que você vende` antes da próxima call, e `/reuniao-fim` no final. Para ver como funciona sem reunião: `/reuniao-demo`.
