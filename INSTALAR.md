# Instalar o Copiloto de Reunião

## Jeito mais fácil: peça para o seu Claude

Abra o **Claude Code** no seu computador e cole esta mensagem:

```
Instala pra mim o Copiloto de Reunião: https://github.com/marcusforti/copiloto-reuniao
Siga o arquivo INSTALAR.md do repositório.
```

Ele faz tudo e no final testa o seu microfone.

## Instruções para o agente (Claude Code)

Se você é o Claude Code e o usuário pediu para instalar este repositório, faça na ordem:

1. Adicione o marketplace e instale o plugin (no terminal, não interativo):
   ```
   claude plugin marketplace add marcusforti/copiloto-reuniao
   claude plugin install copiloto-reuniao@copiloto-reuniao
   ```
   Se o `claude` não estiver no PATH, peça ao usuário para digitar `/plugin marketplace add marcusforti/copiloto-reuniao` e depois `/plugin install copiloto-reuniao@copiloto-reuniao`.
2. Descubra a pasta instalada do plugin: rode `claude plugin list` e procure `copiloto-reuniao`. A pasta costuma ficar em `~/.claude/plugins/`. Se não encontrar, clone o repositório em `~/CopilotoReuniao/app` e use essa pasta.
3. Confira o Python 3.10+:
   - **Windows sem Python:** `winget install -e --id Python.Python.3.12`.
   - **Mac sem Python:** `brew install python@3.12`.
4. Rode `python "<pasta-do-plugin>/motor/copiloto.py" instalar` (Mac: `python3`). Na primeira vez leva alguns minutos, porque baixa as bibliotecas e o modelo de transcrição.
5. **Mac:** rode `bash "<pasta-do-plugin>/instalar/instalar-mac.sh"` e guie o usuário no passo do Multi-Output Device.
6. Pergunte se o usuário quer o modo **grátis** (transcrição no PC) ou **pago** (Deepgram ou Soniox, com a chave dele). Veja `commands/reuniao-instalar.md` para os detalhes.
7. Rode `python "<pasta-do-plugin>/motor/copiloto.py" teste --transcrever` com o usuário falando uma frase.
7b. **Perfil do negócio:** siga `commands/reuniao-perfil.md`. Pergunte se a pessoa já tem script de vendas ou material escrito (colar o texto ou indicar o arquivo) e faça a entrevista curta sobre ofertas, preços, cliente, objeções e provas. Grave em `~/CopilotoReuniao/perfil/perfil.md` (modelo em `skills/copiloto-reuniao/perfil-modelo.md`).
8. Explique ao usuário:
   - Reinicie o Claude Code para os comandos aparecerem.
   - Antes da call: `/reuniao venda NomeDoCliente o que você vende e por quanto`.
   - No fim: `/reuniao-fim`.
   - Para ver sem reunião: `/reuniao-demo`.

## Instalação manual

```
/plugin marketplace add marcusforti/copiloto-reuniao
/plugin install copiloto-reuniao@copiloto-reuniao
```

Reinicie o Claude Code e rode `/reuniao-instalar`.

## Requisitos

- Claude Code, com qualquer plano pago do Claude.
- Windows 10/11 ou macOS 13+.
- Python 3.10 ou mais novo.
- Modo grátis: uns 2 GB de RAM livres durante a reunião. Funciona bem num i5/i7 de 4 núcleos.
- Modo pago: uma chave da Deepgram (conta nova ganha US$ 200) ou da Soniox.
