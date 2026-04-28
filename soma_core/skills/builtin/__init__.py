"""Built-in native skills for Soma."""
from __future__ import annotations

from soma_core.skills.builtin.system import SYSTEM_SKILLS
from soma_core.skills.builtin.network import NETWORK_SKILLS
from soma_core.skills.builtin.repo import REPO_SKILLS
from soma_core.skills.builtin.memory import MEMORY_SKILLS
from soma_core.skills.builtin.mind import MIND_SKILLS
from soma_core.skills.builtin.avatar import AVATAR_SKILLS

ALL_BUILTIN_SKILLS = SYSTEM_SKILLS + NETWORK_SKILLS + REPO_SKILLS + MEMORY_SKILLS + MIND_SKILLS + AVATAR_SKILLS
