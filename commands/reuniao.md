---
description: Liga o copiloto ao vivo para uma reunião (venda, mentoria, diagnóstico) com painel de conselhos
argument-hint: "[venda|mentoria|diagnostico|geral] [nome do cliente] [o que você vende / objetivo]"
---

Ative a skill `copiloto-reuniao` e siga estes passos SEM enrolar (o usuário pode estar entrando na call agora):

`COP` = `python "${CLAUDE_PLUGIN_ROOT}/motor/copiloto.py"` (Mac/Linux: `python3`).

1. **Pronto?** Rode `COP verificar --json`. Se `pronto` for false, avise em uma linha e siga o `/reuniao-instalar` (a instalação leva alguns minutos).

2. **Briefing.** Argumentos recebidos: `$ARGUMENTS`
   - Extraia: modo (venda, mentoria, diagnostico ou geral; padrão venda), cliente, empresa, oferta, preço, objetivo e termos/nomes próprios importantes.
   - Se faltar o essencial (com quem é a reunião e o que se quer dela), pergunte numa única mensagem curta: "Com quem é, o que você quer dessa call e (se for venda) o que oferece e por quanto? Pode responder numa linha, ou 'pular'." Se o usuário disser "pular" ou "rápido", siga com o que tiver.
   - Se houver na pasta atual material do cliente (anotações, proposta, reunião anterior), dê uma olhada rápida para enriquecer o briefing. Não gaste mais de um minuto nisso.

3. **Ligar.** Rode:
   `COP iniciar --modo <modo> --cliente "<cliente>" --empresa "<empresa>" --oferta "<oferta>" --preco "<preço>" --objetivo "<objetivo>" --contexto "<resumo do que você sabe do cliente>" --vocabulario "<nomes,termos>"`
   (omita flags vazias). Guarde `SESSAO=` e `CONSELHOS=` da saída.

4. **Avise o usuário** em poucas linhas: painel aberto no navegador, link do celular (`CELULAR=`), qual microfone e quais saídas estão sendo ouvidos, e o lembrete de compartilhar só a aba ou janela, nunca a tela inteira.

5. **Escreva o primeiro `conselhos.json`** já personalizado com o briefing (fase inicial do modo, a primeira coisa a falar, 3 perguntas de abertura).

6. **Arme o Monitor**: comando `COP acompanhar --sessao "<SESSAO>"`, descrição "falas da reunião", `timeout_ms` 1800000. A cada evento, atualize o `conselhos.json` (veja a skill). Re-arme quando expirar até chegar `[COPILOTO FIM]`.
