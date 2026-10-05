---
description: Testa microfone e áudio do PC antes da reunião (medidor ao vivo + transcrição de teste)
---

`COP` = `python "${CLAUDE_PLUGIN_ROOT}/motor/copiloto.py"` (Mac/Linux: `python3`).

1. Diga ao usuário: "Vou ouvir por 8 segundos: fale uma frase qualquer (ex.: 'testando, um, dois, três'). Vou tocar um som baixinho para testar o áudio do PC."
2. Rode `COP teste --transcrever --json`.
3. Interprete o `JSON:` da saída em linguagem simples:
   - **Microfone OK** e o que o copiloto entendeu ("Entendi você dizer: …").
   - **Áudio do PC OK** (é por onde chega a voz do cliente).
   - Se algo falhou, a correção mais provável:
     - **Windows, microfone sem som:** em Configurações > Sistema > Som, escolha o microfone que você usa na call e defina como "padrão de comunicação". Com fone Bluetooth, entre na call antes de testar (o Windows troca para o modo "viva-voz").
     - **Windows, áudio do PC sem som:** volume no mudo, ou saída diferente da padrão. Teste tocando um vídeo.
     - **Mac, áudio do PC sem som:** precisa do BlackHole e de um Multi-Output Device (`instalar/instalar-mac.sh` explica o passo a passo).
4. Se der para corrigir a configuração (`COP config microfone "parte do nome"` ou `COP config saida "parte do nome"`), proponha e rode de novo.
