#!/usr/bin/env python3
"""
Karajan - hook do Claude Code (UserPromptSubmit)
Classifica cada pedido, registra em logs/ e injeta a etiqueta no contexto.
Não troca o modelo da conversa (hook não consegue); só sugere o nível. Silencioso e
fail-safe de propósito (nunca deve bloquear ou atrasar o pedido do usuário).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

try:
    from orchestrator import Karajan

    data = json.load(sys.stdin)
    prompt = data.get("prompt", "")

    if prompt:
        karajan = Karajan()
        decision = karajan.get_model(prompt)
        karajan.log_decision(prompt, decision)

        # Injeta o nível em todo pedido. Quem aplica a escada de preço é a
        # própria IA, delegando a subagentes conforme o KARAJAN.md.
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"[karajan:{decision['level']}] Escada de preço: ver KARAJAN.md."
            }
        }))
except Exception:
    pass

sys.exit(0)
