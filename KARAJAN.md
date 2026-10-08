# Protocolo Karajan (escada de preço)

Este arquivo é a instrução que a IA lê. Copie para `~/.claude/KARAJAN.md` e
referencie no seu `~/.claude/CLAUDE.md` com uma linha `@KARAJAN.md`.

Um hook classifica cada pedido por palavra-chave e injeta
`[karajan:cheap|balanced|powerful]` no contexto. Ele **só classifica**: não
troca o modelo da conversa (hook não consegue). Quem aplica a escada é você,
delegando a subagentes.

## Regra: o mais barato que resolve

Escada de preço, sempre do degrau mais baixo para o mais alto:

1. **Modelo simples** (`cheap`): coisas simples. `Agent` com `model: "haiku"`.
2. **Modelo intermediário** (`balanced`): o padrão do trabalho real. `Agent`
   com `model: "sonnet"`.
3. **Modelo mais forte** (`powerful`, a conversa principal): só quando os de
   baixo não dão conta.

A etiqueta é o ponto de partida; você julga e pode subir **ou descer** um
degrau. Na dúvida entre dois degraus, fique com o mais barato. Se o resultado
do subagente vier fraco, suba um degrau e refaça (não entregue resultado ruim
para economizar).

## Que degrau usar

- **Simples:** "o que é X", explicação curta, busca, listar ou ler arquivos,
  resumir, traduzir, formatar, reescrita curta, checagens mecânicas.
- **Intermediário:** escrever textos; editar código; scripts; debug comum;
  pesquisa na web com síntese; tarefas com vários passos mas bem definidas.
- **Mais forte (direto, sem delegar):** arquitetura, decisões de projeto que
  afetam vários arquivos, estratégia, depuração difícil, revisão final de algo
  importante, e quando a tarefa depende muito do contexto já acumulado na
  conversa.

## Como delegar

- Escreva um pedido autocontido (caminhos, objetivo, formato da resposta e as
  regras do usuário que valem para a tarefa).
- Tarefa grande pode ser dividida: o modelo simples faz a leitura e o
  levantamento, o intermediário escreve, você revisa e decide.
- Repasse o resultado sem reprocessar tudo de novo.
- **Não compensa delegar** quando seria preciso recopiar tanto contexto que
  anula a economia, ou quando a resposta é uma linha que você já sabe.

## Monitoramento

```bash
bash scripts/karajan.sh stats        # distribuição dos níveis e economia estimada
bash scripts/karajan.sh history 20   # últimas decisões
```

Os números de economia são estimativa pela proporção de preço definida em
`config/routes.json`, não tokens reais medidos.
