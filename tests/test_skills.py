"""Tests for the skill system."""

from __future__ import annotations

import pytest

from custom_components.voice_agent_router.skills.loader import SkillLoader


@pytest.mark.asyncio
async def test_load_skills(skills_dir):
    loader = SkillLoader(skills_dir)
    await loader.async_load()
    assert len(loader.skills) == 2
    assert "test_skill" in loader.skills
    assert "llm_skill" in loader.skills


@pytest.mark.asyncio
async def test_skill_match(skills_dir):
    loader = SkillLoader(skills_dir)
    await loader.async_load()

    match = loader.match("please test me now")
    assert match is not None
    assert match.name == "test_skill"
    assert not match.requires_llm


@pytest.mark.asyncio
async def test_skill_match_llm(skills_dir):
    loader = SkillLoader(skills_dir)
    await loader.async_load()

    match = loader.match("do a smart test")
    assert match is not None
    assert match.name == "llm_skill"
    assert match.requires_llm


@pytest.mark.asyncio
async def test_skill_no_match(skills_dir):
    loader = SkillLoader(skills_dir)
    await loader.async_load()

    match = loader.match("something completely different")
    assert match is None


@pytest.mark.asyncio
async def test_reload_skills(skills_dir):
    loader = SkillLoader(skills_dir)
    await loader.async_load()
    assert len(loader.skills) == 2

    # Add a new skill file
    new_skill = skills_dir / "new_skill.yaml"
    new_skill.write_text("""
name: new_skill
description: "A new skill"
trigger:
  patterns: ["new thing"]
requires_llm: false
response_template: "New skill!"
""")

    await loader.async_reload()
    assert len(loader.skills) == 3


@pytest.mark.asyncio
async def test_empty_directory(tmp_path):
    loader = SkillLoader(tmp_path)
    await loader.async_load()
    assert len(loader.skills) == 0


@pytest.mark.asyncio
async def test_nonexistent_directory(tmp_path):
    loader = SkillLoader(tmp_path / "nope")
    await loader.async_load()
    assert len(loader.skills) == 0
