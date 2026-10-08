#!/bin/bash
# Karajan - classifica um pedido e mostra o registro das decisões.
# Uso: karajan.sh classify "<pedido>" | stats | history [N] | bandit | outcome <nível> <success|fail>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KARAJAN_HOME="$(dirname "$SCRIPT_DIR")"

show_help() {
    cat << EOF
Karajan - escada de preço dos modelos

  karajan.sh classify "<pedido>"        # nível e modelo sugeridos para o pedido
  karajan.sh stats                      # distribuição dos níveis e economia estimada
  karajan.sh history [N]                # últimas N decisões (padrão: 10)
  karajan.sh bandit                     # taxa de sucesso aprendida por nível
  karajan.sh outcome <nível> success    # o nível sugerido bastou
  karajan.sh outcome <nível> fail       # o nível sugerido não bastou

A economia é estimativa pela proporção de preço em config/routes.json,
não gasto medido.
EOF
}

run_python() {
    KARAJAN_SCRIPTS="$SCRIPT_DIR" python3 - "$@"
}

case "${1:-help}" in
    help|-h|--help)
        show_help
        ;;
    classify)
        if [ $# -lt 2 ]; then
            echo "Uso: karajan.sh classify \"<pedido>\""
            exit 1
        fi
        python3 "$SCRIPT_DIR/orchestrator.py" "$2"
        ;;
    stats)
        run_python << 'PY'
import os, sys
sys.path.insert(0, os.environ["KARAJAN_SCRIPTS"])
from orchestrator import Karajan

report = Karajan().get_savings_report()
if "distribution" not in report:
    print("Nenhuma decisão registrada ainda")
    sys.exit(0)

dist = report["distribution"]
print("Decisões por nível:")
for level in ("cheap", "balanced", "powerful"):
    print(f"  {level:>8}: {dist.get(level, 0):>5}")
print(f"Total: {report['total_tasks']}")
print(f"Economia estimada contra usar sempre o nível mais caro: ~{report['savings_percent']}%")
print("(estimativa pela proporção de preço, não gasto medido)")
PY
        ;;
    history)
        history_file="$KARAJAN_HOME/logs/history.jsonl"
        if [ ! -f "$history_file" ]; then
            echo "Nenhuma decisão registrada ainda"
            exit 0
        fi
        tail -n "${2:-10}" "$history_file" | python3 -c '
import sys, json
for i, line in enumerate(sys.stdin, 1):
    data = json.loads(line)
    level = data["decision"]["level"]
    preview = data["prompt_preview"]
    print(f"{i}. [{level:>8}] {preview}")
'
        ;;
    bandit)
        run_python << 'PY'
import os, sys
sys.path.insert(0, os.environ["KARAJAN_SCRIPTS"])
from orchestrator import Karajan, BANDIT_MIN_SAMPLES

for level, data in Karajan().get_bandit_report().items():
    status = "aprendendo" if data["learning"] else f"poucas amostras ({data['samples']}/{BANDIT_MIN_SAMPLES})"
    print(f"  {level:>8}: {data['success_rate'] * 100:>5.1f}%  [{status}]")
PY
        ;;
    outcome)
        if [ $# -lt 3 ]; then
            echo "Uso: karajan.sh outcome <cheap|balanced|powerful> <success|fail>"
            exit 1
        fi
        run_python "$2" "$3" << 'PY'
import os, sys
sys.path.insert(0, os.environ["KARAJAN_SCRIPTS"])
from orchestrator import Karajan

level, outcome = sys.argv[1], sys.argv[2]
karajan = Karajan()
if level not in karajan.config["models"]:
    sys.exit(f"nível desconhecido: {level}")
karajan.record_outcome(level, outcome)
print(f"Registrado: {level} -> {outcome}")
PY
        ;;
    *)
        show_help
        exit 1
        ;;
esac
