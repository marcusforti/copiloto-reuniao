---
description: Liga o copiloto ao vivo para uma reunião (venda, mentoria, diagnóstico, entrevista) com painel de conselhos
argument-hint: "[venda|mentoria|diagnostico|geral|entrevista] [nome do cliente] [o que você vende / objetivo]"
---

Ative a skill `copiloto-reuniao` e siga estes passos SEM enrolar (o usuário pode estar entrando na call agora):

`COP` = `python "${CLAUDE_PLUGIN_ROOT}/motor/copiloto.py"` (Mac/Linux: `python3`).

1. **Pronto?** Rode `COP verificar --json`. Se `pronto` for false, avise em uma linha e siga o `/reuniao-instalar` (a instalação leva alguns minutos).

2. **Perfil.** Rode `COP perfil --mostrar` e guarde o perfil no contexto: ofertas, preços, cliente ideal, objeções, provas e script. Se houver `script-de-vendas.md` ou outros arquivos na pasta, leia também. Se não existir perfil, siga sem ele e, no fim do passo 4, sugira o `/reuniao-perfil` para a próxima.

3. **Briefing.** Argumentos recebidos: `$ARGUMENTS`
   - Extraia: modo (venda, mentoria, diagnostico, geral ou entrevista; padrão venda), cliente, empresa, oferta, preço, objetivo e termos/nomes próprios importantes.
   - **Com perfil, a oferta e o preço já vêm de lá.** Se houver mais de uma oferta e não estiver claro qual é, pergunte só isso.
   - Se faltar o essencial (com quem é a reunião e o que se quer dela), pergunte numa única mensagem curta: "Com quem é, o que você quer dessa call e (se for venda e não estiver no seu perfil) o que oferece e por quanto? Pode responder numa linha, ou 'pular'." Se o usuário disser "pular" ou "rápido", siga com o que tiver.
   - **Presencial:** se a pessoa estiver na mesma sala, inclua `--presencial` no passo 4 (ou `--presencial "<parte do nome do microfone>"`). Um segundo microfone, de preferência a webcam, vira o canal da outra pessoa.
   - Se houver na pasta atual material do cliente (anotações, proposta, reunião anterior), dê uma olhada rápida para enriquecer o briefing. Não gaste mais de um minuto nisso.

4. **Ligar.** Rode:
   `COP iniciar --modo <modo> --cliente "<cliente>" --empresa "<empresa>" --oferta "<oferta>" --preco "<preço>" --objetivo "<objetivo>" --contexto "<resumo do que você sabe do cliente>" --vocabulario "<nomes,termos>"` [`--cola "<arquivo.json>"`]
   (omita flags vazias; os termos do perfil já entram sozinhos). **Cola:** se existir material de preparação (playbook, perguntas e respostas, objeções), monte antes um `cola.json` com `{"itens": [{"titulo": "Salário", "gatilhos": ["salário", "pretensão", "quanto você quer"], "resposta": "…"}]}` (gatilhos em minúsculas, como a pessoa falaria; resposta em até 6 linhas) e passe em `--cola`. Sem `--cola`, usa `perfil/cola.json` se existir. Guarde `SESSAO=` e `CONSELHOS=` da saída.

5. **Avise o usuário** em poucas linhas: painel aberto no navegador, link do celular (`CELULAR=`), qual microfone e quais saídas estão sendo ouvidos, e o lembrete de compartilhar só a aba ou janela, nunca a tela inteira. No presencial, troque o lembrete por: não deixe o painel virado para a pessoa.

6. **Escreva o primeiro `conselhos.json`** já personalizado (com `tema`): fase inicial (se o usuário tem script, use as etapas dele como fases no campo `fases`), a primeira coisa a falar e 3 perguntas de abertura no estilo do script dele.

7. **Arme o Monitor**: comando `COP acompanhar --sessao "<SESSAO>"`, descrição "falas da reunião", `timeout_ms` 1800000. A cada evento, atualize o `conselhos.json` (veja a skill: conselho por contexto, `tema` estável, `RESPONDA:` quando perguntarem), usando o perfil: ofertas e preços reais, as respostas de objeção que o usuário já usa, as provas dele e as etapas do script. Re-arme quando expirar até chegar `[COPILOTO FIM]`.
