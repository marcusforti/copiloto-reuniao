# Formato dos conselhos (conselhos.json)

O painel lê `conselhos.json` na pasta da sessão. Sempre escreva o arquivo INTEIRO, em JSON válido, com estes campos:

```json
{
  "fase": "Diagnóstico",
  "agora": "Pergunte quanto custa para ela uma semana com metade da agenda vazia.",
  "porque": "Ela tem a dor mas ainda não deu número. Dor sem número não justifica investimento.",
  "perguntas": ["Quanto você deixa de faturar numa semana fraca?", "O que você já tentou?", "Quem decide além de você?"],
  "sinais": ["DOR: agenda irregular", "NÚMERO: perde ~R$ 8 mil/mês", "DECISOR: marido participa"],
  "objecoes": [{"objecao": "Achei caro", "resposta": "Separe preço de medo: pergunte o que deu errado da última vez e faça a conta do retorno com ela."}],
  "evitar": ["Dar desconto agora", "Falar mal do concorrente"],
  "atualizado": "14:32"
}
```

## Regras de ouro

- **`agora`**: a PRÓXIMA coisa a falar ou fazer, em até 25 palavras, imperativo direto ("Pergunte…", "Confirme…", "Não responda o preço ainda: …"). É lido de relance, no meio da conversa. Nada de "você poderia considerar".
- **`porque`**: em até 30 palavras, o motivo, citando o que a outra pessoa acabou de dizer.
- **Só troque o `agora` quando a conversa avançou** (nova informação, nova pergunta, nova objeção, mudança de fase). Se nada mudou, mantenha o mesmo texto: o painel destaca cada troca, e troca demais distrai.
- **Quando o cliente fizer uma pergunta ou objeção, responda a isso primeiro** no `agora`, com a frase pronta ou o caminho.
- **`perguntas`**: 2 a 4 perguntas abertas e específicas para os próximos minutos. Tire as que já foram feitas.
- **`sinais`**: o que o cliente revelou, no formato `ETIQUETA: fato`, mais importante primeiro, no máximo 10. Etiquetas: `DOR`, `DESEJO`, `NÚMERO`, `PRAZO`, `DECISOR`, `ORÇAMENTO`, `OBJEÇÃO`, `CONCORRENTE`, `SIM` (sinal de compra), `RISCO`, `PRÓXIMO PASSO`, `VITÓRIA`.
- **`objecoes`**: as objeções que apareceram e a melhor resposta para cada uma. A mais recente primeiro.
- **`evitar`**: 1 a 3 armadilhas para agora.
- **`fase`**: uma das fases do modo (ver o arquivo do modo). Avance quando a conversa avançar; pode voltar.
- **`fases`** (opcional): lista com as etapas do script do usuário, se ele tiver um (ex.: `["Conexão", "Diagnóstico", "Pitch", "Fechamento"]`). O painel mostra essas etapas no topo no lugar das fases padrão do modo; aí `fase` deve ser uma delas.
- **Use os números e as palavras do cliente.** Conselho genérico não serve: "Pergunte sobre a dor" é ruim; "Pergunte quanto ela perde nas semanas fracas" é bom.
- **Nunca invente fatos**: preço, prazo, garantia e condições só os que estão no briefing ou foram ditos na call. Se faltar, o conselho é perguntar ou dizer que confirma depois.
- **Transcrição automática erra.** Se uma frase não fizer sentido, ignore ou interprete pelo contexto; não construa conselho em cima de uma palavra estranha.
- **Dados sensíveis** (saúde, religião, vida íntima, dados de terceiros) não entram em `sinais`. A pessoa pode citar, mas o painel e o resumo não guardam.
