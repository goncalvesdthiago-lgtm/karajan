# Karajan

Escada de preço para o Claude Code: cada pedido ganha uma etiqueta (simples,
médio ou difícil) e a IA usa o modelo mais barato que resolve.

## O problema

O modelo mais forte custa várias vezes o mais simples, e a maior parte do que
se pede num dia é simples: achar um arquivo, resumir, formatar, traduzir.
Deixar tudo no modelo mais forte é pagar caro por tarefa barata.

## Como funciona

1. Um hook do Claude Code (`hooks/karajan_hook.py`) roda a cada pedido.
2. Ele classifica o pedido por palavra-chave e tamanho (`scripts/orchestrator.py`,
   regras em `config/routes.json`) em `cheap`, `balanced` ou `powerful`.
3. A decisão é gravada em `logs/` e a etiqueta entra no contexto da conversa,
   por exemplo `[karajan:cheap]`.
4. A IA lê o `KARAJAN.md`, que diz o que fazer com a etiqueta: delegar o
   trabalho a um subagente do degrau certo e subir um degrau se o resultado
   vier fraco.

## O que ele não faz

- **Não troca o modelo da conversa.** Um hook não consegue fazer isso. O
  script só classifica; quem delega é a própria IA, seguindo o `KARAJAN.md`.
- **Não acerta sempre.** O classificador é por palavra-chave, então erra. Por
  isso a etiqueta é sugestão, não ordem, e a IA pode subir ou descer um degrau.
- **Não mede gasto real.** A economia mostrada em `stats` é estimativa pela
  proporção de preço entre os níveis (`token_weights`), não tokens medidos.

## Instalação

Precisa de Python 3 e do Claude Code.

```bash
git clone https://github.com/goncalvesdthiago-lgtm/karajan.git ~/karajan
cp ~/karajan/KARAJAN.md ~/.claude/KARAJAN.md
echo '@KARAJAN.md' >> ~/.claude/CLAUDE.md
```

Depois ligue o hook em `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/karajan/hooks/karajan_hook.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

Abra uma sessão nova, faça um pedido e confira se o registro está enchendo:

```bash
bash ~/karajan/scripts/karajan.sh history
```

Esse passo importa. Uma automação instalada que não grava nada no registro
não está ligada, por mais que a documentação diga que está.

## Uso

```bash
bash scripts/karajan.sh classify "o que é um hook"   # nível e modelo sugeridos
bash scripts/karajan.sh stats                         # distribuição e economia estimada
bash scripts/karajan.sh history 20                    # últimas decisões
bash scripts/karajan.sh outcome cheap fail            # o nível sugerido não bastou
bash scripts/karajan.sh bandit                        # taxa de sucesso aprendida por nível
```

Com pelo menos cinco resultados registrados em `outcome` para um nível, o
classificador passa a subir um degrau sozinho quando a taxa de sucesso daquele
nível está baixa.

## Ajuste para o seu uso

Tudo fica em `config/routes.json`:

- `models`: o modelo de cada degrau.
- `token_weights`: a proporção de preço entre os degraus, usada só na estimativa.
- `classification_rules`: as palavras-chave de cada nível. As que vêm no
  arquivo são as que funcionam para o meu trabalho, em português; troque pelas
  do seu.

O `logs/history.jsonl` guarda o começo de cada pedido que você fez. Ele fica
fora do git por padrão; não publique esse arquivo.
