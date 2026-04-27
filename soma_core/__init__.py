"""
soma_core — Volitional Soma Core: goal-directed cognition for the Latent Somatic agent.
"""

from soma_core.config import CFG, SomaConfig
from soma_core.goals import GoalStore
from soma_core.memory import SomaMemory
from soma_core.reflection import ReflectionEngine
from soma_core.drives import compute_drives
from soma_core.policy import select_policy
from soma_core.actions import select_actions
from soma_core.growth import compute_growth
from soma_core.trace import CognitiveTrace
from soma_core.llm_core import call_llm, build_llm_context
from soma_core.mind import SomaMind
from soma_core.executor import AutonomousShellExecutor, CommandBlocked
from soma_core.self_modify import AutonomousSelfModifier

__all__ = [
    "CFG", "SomaConfig",
    "GoalStore", "SomaMemory", "ReflectionEngine",
    "compute_drives", "select_policy", "select_actions",
    "compute_growth", "CognitiveTrace",
    "call_llm", "build_llm_context",
    "SomaMind",
    "AutonomousShellExecutor", "CommandBlocked",
    "AutonomousSelfModifier",
]
