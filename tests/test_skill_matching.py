"""Tests for skill matching improvements — fuzzy scoring and near-miss detection."""

from __future__ import annotations

import pytest

from custom_components.voice_agent_router.skills.loader import SkillLoader


@pytest.fixture
def good_morning_skills_dir(tmp_path):
    """Create a skills directory with a good_morning skill."""
    skill = tmp_path / "good_morning.yaml"
    skill.write_text("""
name: good_morning
description: "Good morning routine"
trigger:
  patterns: ["good morning"]
requires_llm: false
response_template: "Good morning! Starting your routine."
entities: []
""")
    return tmp_path


@pytest.fixture
def multi_skills_dir(tmp_path):
    """Create a skills directory with multiple skills for disambiguation tests."""
    gm = tmp_path / "good_morning.yaml"
    gm.write_text("""
name: good_morning
description: "Good morning routine"
trigger:
  patterns: ["good morning", "morning routine"]
requires_llm: false
response_template: "Good morning! Starting your routine."
entities: []
""")
    lights = tmp_path / "lights.yaml"
    lights.write_text("""
name: lights_control
description: "Control lights"
trigger:
  patterns: ["turn on the lights", "turn off the lights"]
requires_llm: false
response_template: "Lights adjusted."
entities: []
""")
    return tmp_path


# --- Exact substring match ---


@pytest.mark.asyncio
async def test_exact_substring_match(good_morning_skills_dir):
    """Exact substring 'good morning' matches the good_morning skill."""
    loader = SkillLoader(good_morning_skills_dir)
    await loader.async_load()

    result = loader.match("good morning")
    assert result is not None
    assert result.name == "good_morning"


@pytest.mark.asyncio
async def test_exact_substring_match_with_score(good_morning_skills_dir):
    """Exact substring match returns score 1.0."""
    loader = SkillLoader(good_morning_skills_dir)
    await loader.async_load()

    result = loader.match_with_score("good morning")
    assert result is not None
    skill, score = result
    assert skill.name == "good_morning"
    assert score == 1.0


@pytest.mark.asyncio
async def test_exact_substring_embedded(good_morning_skills_dir):
    """Substring match works when pattern is embedded in longer input."""
    loader = SkillLoader(good_morning_skills_dir)
    await loader.async_load()

    result = loader.match_with_score("say good morning to everyone")
    assert result is not None
    skill, score = result
    assert skill.name == "good_morning"
    assert score == 1.0


# --- Fuzzy token-overlap match ---


@pytest.mark.asyncio
async def test_fuzzy_match_extra_token(good_morning_skills_dir):
    """'good morning everyone' contains substring 'good morning', so fast-path matches."""
    loader = SkillLoader(good_morning_skills_dir)
    await loader.async_load()

    # "good morning everyone" contains "good morning" as substring -> fast path, score 1.0
    result = loader.match_with_score("good morning everyone", threshold=0.6)
    assert result is not None
    skill, score = result
    assert skill.name == "good_morning"
    assert score == 1.0


@pytest.mark.asyncio
async def test_fuzzy_match_reworded(good_morning_skills_dir):
    """'morning good vibes' fuzzy-matches 'good morning' via token overlap."""
    loader = SkillLoader(good_morning_skills_dir)
    await loader.async_load()

    # "morning good vibes" — tokens {morning, good, vibes}
    # pattern "good morning" — tokens {good, morning}
    # overlap=2, max(3,2)=3, score=2/3=0.667
    result = loader.match_with_score("morning good vibes", threshold=0.6)
    assert result is not None
    skill, score = result
    assert skill.name == "good_morning"
    assert abs(score - 2 / 3) < 0.01


@pytest.mark.asyncio
async def test_fuzzy_match_high_overlap(good_morning_skills_dir):
    """Input that is very close to a pattern matches at default threshold."""
    loader = SkillLoader(good_morning_skills_dir)
    await loader.async_load()

    # "good morning" is exact substring of itself, so it takes the fast path
    result = loader.match_with_score("good morning")
    assert result is not None
    assert result[1] == 1.0


# --- False positive guard ---


@pytest.mark.asyncio
async def test_no_false_positive(good_morning_skills_dir):
    """'turn on the lights' does NOT match 'good morning' skill."""
    loader = SkillLoader(good_morning_skills_dir)
    await loader.async_load()

    result = loader.match("turn on the lights")
    assert result is None


@pytest.mark.asyncio
async def test_no_false_positive_with_score(good_morning_skills_dir):
    """'turn on the lights' has no overlap with 'good morning' pattern."""
    loader = SkillLoader(good_morning_skills_dir)
    await loader.async_load()

    result = loader.match_with_score("turn on the lights")
    assert result is None


# --- No match ---


@pytest.mark.asyncio
async def test_no_match_empty_skills(tmp_path):
    """No match when there are no skills loaded."""
    loader = SkillLoader(tmp_path)
    await loader.async_load()

    result = loader.match("good morning")
    assert result is None


@pytest.mark.asyncio
async def test_no_match_unrelated(multi_skills_dir):
    """Completely unrelated input returns None."""
    loader = SkillLoader(multi_skills_dir)
    await loader.async_load()

    result = loader.match("what is the weather like")
    assert result is None


# --- Near-miss detection ---


@pytest.mark.asyncio
async def test_near_miss_detection(multi_skills_dir):
    """Input with partial overlap (0.4 < score < 0.8) triggers near-miss."""
    loader = SkillLoader(multi_skills_dir)
    await loader.async_load()

    # "good morning everyone please" — tokens {good, morning, everyone, please}
    # pattern "good morning" — tokens {good, morning}
    # overlap=2, max(4,2)=4, score=0.5 — in (0.4, 0.8) range
    near = loader.nearest_miss("good morning everyone please")
    assert near is not None
    name, score = near
    assert name == "good_morning"
    assert 0.4 < score < 0.8


@pytest.mark.asyncio
async def test_near_miss_none_for_exact(good_morning_skills_dir):
    """No near-miss when text is an exact match (score >= 0.8)."""
    loader = SkillLoader(good_morning_skills_dir)
    await loader.async_load()

    # "good morning" is a substring match, token score would be 1.0
    near = loader.nearest_miss("good morning")
    assert near is None


@pytest.mark.asyncio
async def test_near_miss_none_for_no_overlap(good_morning_skills_dir):
    """No near-miss when text has zero overlap (score <= 0.4)."""
    loader = SkillLoader(good_morning_skills_dir)
    await loader.async_load()

    near = loader.nearest_miss("turn on the lights")
    assert near is None


# --- match_with_score returns correct scores ---


@pytest.mark.asyncio
async def test_score_calculation(multi_skills_dir):
    """Verify score calculation for various inputs."""
    loader = SkillLoader(multi_skills_dir)
    await loader.async_load()

    # Exact substring: score 1.0
    result = loader.match_with_score("good morning")
    assert result is not None
    assert result[1] == 1.0

    # "turn on the lights now" contains "turn on the lights" as substring: score 1.0
    result = loader.match_with_score("turn on the lights now")
    assert result is not None
    assert result[1] == 1.0


@pytest.mark.asyncio
async def test_fuzzy_score_values(good_morning_skills_dir):
    """Verify exact fuzzy score values."""
    loader = SkillLoader(good_morning_skills_dir)
    await loader.async_load()

    # "morning routine check" — tokens {morning, routine, check}
    # pattern "good morning" — tokens {good, morning}
    # overlap=1 (morning), max(3,2)=3, score=1/3 ~ 0.33
    result = loader.match_with_score("morning routine check", threshold=0.3)
    assert result is not None
    skill, score = result
    assert abs(score - 1 / 3) < 0.01
