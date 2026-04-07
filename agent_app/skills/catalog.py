from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SkillMetadata:
    name: str
    description: str
    skill_dir: str
    skill_md_path: str

    def to_public_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "description": self.description,
        }


def _skills_dir() -> Path:
    return Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def get_registered_skills() -> tuple[SkillMetadata, ...]:
    import frontmatter

    skills_dir = _skills_dir()
    if not skills_dir.exists():
        return ()

    skills: list[SkillMetadata] = []
    for skill_dir in sorted(
        path for path in skills_dir.iterdir() if path.is_dir() and (path / "SKILL.md").exists()
    ):
        skill_md_path = skill_dir / "SKILL.md"
        post = frontmatter.load(skill_md_path)
        name = str(post.get("name") or "").strip()
        description = str(post.get("description") or "").strip()
        if not name or not description:
            raise ValueError(
                f"{skill_md_path} 缺少合法的 name/description frontmatter，无法注册 skill。"
            )

        skills.append(
            SkillMetadata(
                name=name,
                description=description,
                skill_dir=str(skill_dir.resolve()),
                skill_md_path=str(skill_md_path.resolve()),
            )
        )

    return tuple(skills)


def get_registered_skill(skill_name: str) -> SkillMetadata | None:
    normalized_name = skill_name.strip()
    for skill in get_registered_skills():
        if skill.name == normalized_name:
            return skill
    return None
