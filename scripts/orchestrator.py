#!/usr/bin/env python3
"""
Karajan - Modelo Orquestrador Inteligente
Roteia tarefas para o modelo certo, economizando tokens
"""

import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path

# Thompson sampling: nível é escalado automaticamente só depois de acumular
# amostras suficientes (evita escalar no cold start, onde Beta(1,1) é só
# uma moeda ao ar). Abaixo desse número de observações, a config estática
# de routes.json manda sozinha.
BANDIT_MIN_SAMPLES = 5
# Se a média aprendida (alpha / (alpha+beta)) cair abaixo disso com amostras
# suficientes, o nível escolhido é tratado como historicamente insuficiente
# para essa tarefa e a escala definida em fallback_strategy é acionada.
BANDIT_ESCALATION_FLOOR = 0.5


class Karajan:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "routes.json"

        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.logs_dir = Path(__file__).parent.parent / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        self.stats_file = self.logs_dir / "stats.json"
        self.history_file = self.logs_dir / "history.jsonl"
        self.bandit_file = self.logs_dir / "bandit_state.json"

    def _load_config(self):
        with open(self.config_path) as f:
            return json.load(f)

    def _load_bandit_state(self) -> dict:
        if not self.bandit_file.exists():
            return {}
        with open(self.bandit_file) as f:
            return json.load(f)

    def _save_bandit_state(self, state: dict):
        with open(self.bandit_file, "w") as f:
            json.dump(state, f, indent=2)

    def classify_task(self, prompt: str, context_size: dict = None) -> str:
        """
        Classifica a tarefa e retorna o nível de modelo necessário.
        Returns: "cheap", "balanced", ou "powerful"
        """
        prompt_lower = prompt.lower()
        context_size = context_size or {}

        # Verificar palavras-chave de nível powerful
        for keyword in self.config["classification_rules"]["powerful_keywords"]:
            if keyword in prompt_lower:
                return "powerful"

        # Verificar limites de contexto
        files = context_size.get("files", 0)
        lines = context_size.get("lines", 0)

        balanced_max_files = self.config["context_thresholds"]["balanced_max_files"]
        balanced_max_lines = self.config["context_thresholds"]["balanced_max_lines"]
        cheap_max_files = self.config["context_thresholds"]["cheap_max_files"]
        cheap_max_lines = self.config["context_thresholds"]["cheap_max_lines"]

        if files > balanced_max_files or lines > balanced_max_lines:
            return "powerful"

        # Verificar palavras-chave de nível balanced
        for keyword in self.config["classification_rules"]["balanced_keywords"]:
            if keyword in prompt_lower:
                return "balanced"

        if files > cheap_max_files or lines > cheap_max_lines:
            return "balanced"

        # Prompt longo ou com caminho de arquivo raramente é "simples"
        if len(prompt) > 400 or "/users/" in prompt_lower or "~/" in prompt_lower:
            return "balanced"

        # Padrão: cheap (economizador)
        return "cheap"

    def _maybe_escalate(self, level: str) -> tuple[str, bool]:
        """
        Thompson sampling sobre o fallback_strategy já declarado em routes.json.
        Cada nível carrega um Beta(alpha, beta) que aprende sua taxa de sucesso
        real (via record_outcome). Com amostras suficientes e uma amostra ruim,
        escala pro próximo nível definido em fallback_strategy — em vez de só
        confiar nas keywords/thresholds estáticos. Retorna (nivel_final, escalou).
        """
        fallback = self.config.get("fallback_strategy", {})
        if not fallback.get("retry_on_fail"):
            return level, False

        escalate_to = fallback.get(f"escalate_{level}_to")
        if not escalate_to:
            return level, False  # "powerful" não tem pra onde escalar

        state = self._load_bandit_state()
        prior = state.get(level, {"alpha": 1, "beta": 1})
        alpha, beta = prior["alpha"], prior["beta"]

        samples = alpha + beta - 2  # Beta(1,1) = 0 observações reais
        if samples < BANDIT_MIN_SAMPLES:
            return level, False  # cold start: ainda não há evidência suficiente

        drawn = random.betavariate(alpha, beta)
        if drawn < BANDIT_ESCALATION_FLOOR:
            return escalate_to, True

        return level, False

    def get_model(self, prompt: str, context_size: dict = None) -> dict:
        """
        Obtém a recomendação de modelo para a tarefa.
        Retorna: {"level": str, "model": str, "reason": str}
        """
        base_level = self.classify_task(prompt, context_size)
        level, escalated = self._maybe_escalate(base_level)
        model = self.config["models"][level]

        reasons = {
            "cheap": "Tarefa simples - Haiku 4.5 (mais barato)",
            "balanced": "Complexidade média - Sonnet 5.5 (custo-benefício)",
            "powerful": "Tarefa complexa - Opus 5.5 (só quando precisa)"
        }
        reason = reasons[level]
        if escalated:
            reason = f"{reason} (escalado de {base_level}: histórico de sucesso baixo nesse nível)"

        return {
            "level": level,
            "model": model,
            "reason": reason,
            "token_weight": self.config["token_weights"][level],
            "base_level": base_level,
            "escalated": escalated
        }

    def record_outcome(self, level: str, outcome: str):
        """
        Registra se o nível escolhido bastou (success) ou precisou de mais
        (fail/escalated). Atualiza o Beta(alpha, beta) desse nível, usado por
        _maybe_escalate na próxima chamada. outcome: "success" ou "fail".
        """
        if outcome not in ("success", "fail"):
            raise ValueError('outcome deve ser "success" ou "fail"')

        state = self._load_bandit_state()
        prior = state.setdefault(level, {"alpha": 1, "beta": 1})
        if outcome == "success":
            prior["alpha"] += 1
        else:
            prior["beta"] += 1
        self._save_bandit_state(state)

    def log_decision(self, prompt: str, decision: dict, context_size: dict = None):
        """Registra a decisão de roteamento para análise posterior"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "prompt_preview": prompt[:100].replace("\n", " "),
            "decision": decision,
            "context_size": context_size or {}
        }

        # Adicionar ao histórico
        with open(self.history_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        # Atualizar estatísticas
        self._update_stats(decision["level"])

    def _update_stats(self, level: str):
        """Atualiza estatísticas de uso"""
        stats = {}
        if self.stats_file.exists():
            with open(self.stats_file) as f:
                stats = json.load(f)

        stats.setdefault(level, 0)
        stats[level] += 1

        with open(self.stats_file, "w") as f:
            json.dump(stats, f, indent=2)

    def get_savings_report(self):
        """Retorna relatório de economia de tokens"""
        if not self.stats_file.exists():
            return {"message": "Nenhum dado de economia ainda"}

        with open(self.stats_file) as f:
            stats = json.load(f)

        total_uses = sum(stats.values())
        weights = self.config["token_weights"]

        # Calcular economia (baseline = always using powerful)
        baseline_cost = total_uses * weights["powerful"]
        actual_cost = sum(stats.get(level, 0) * weights[level] for level in ["cheap", "balanced", "powerful"])
        savings_percent = ((baseline_cost - actual_cost) / baseline_cost * 100) if baseline_cost > 0 else 0

        return {
            "total_tasks": total_uses,
            "distribution": stats,
            "estimated_baseline_cost": baseline_cost,
            "estimated_actual_cost": actual_cost,
            "savings_percent": round(savings_percent, 1),
            "savings_message": f"🎵 Karajan economizou ~{savings_percent:.0f}% de tokens!"
        }

    def get_bandit_report(self) -> dict:
        """Taxa de sucesso aprendida por nível, a partir do Beta(alpha, beta)."""
        state = self._load_bandit_state()
        report = {}
        for level in self.config["models"]:
            prior = state.get(level, {"alpha": 1, "beta": 1})
            alpha, beta = prior["alpha"], prior["beta"]
            samples = alpha + beta - 2
            report[level] = {
                "samples": samples,
                "success_rate": round(alpha / (alpha + beta), 3),
                "learning": samples >= BANDIT_MIN_SAMPLES
            }
        return report


def main():
    if len(sys.argv) < 2:
        print("Uso: python orchestrator.py <prompt> [--context-files N] [--context-lines N]")
        sys.exit(1)

    prompt = sys.argv[1]

    # Parsear contexto se fornecido
    context_size = {}
    for i, arg in enumerate(sys.argv[2:]):
        if arg == "--context-files" and i + 2 < len(sys.argv):
            context_size["files"] = int(sys.argv[i + 3])
        elif arg == "--context-lines" and i + 2 < len(sys.argv):
            context_size["lines"] = int(sys.argv[i + 3])

    karajan = Karajan()
    decision = karajan.get_model(prompt, context_size)
    karajan.log_decision(prompt, decision, context_size)

    # Output para ser parseado
    print(json.dumps(decision, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
