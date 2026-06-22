"""Tests for the #9 stack-personalization mechanical transform."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.cli import (  # noqa: E402
    _PERSONALIZE_HEADING,
    _inject_personalize,
    _personalize_transform,
    _widen_arg_hint,
)

_SCOPE = "## Scope & Limits\n\nbook only.\n"


def test_inject_before_scope():
    out = _inject_personalize(f"# Skill\n\nbody\n\n---\n\n{_SCOPE}")
    assert _PERSONALIZE_HEADING in out
    assert out.index(_PERSONALIZE_HEADING) < out.index("## Scope & Limits")


def test_inject_appends_when_no_scope():
    out = _inject_personalize("# Skill\n\nonly body, no scope section\n")
    assert out.rstrip().endswith("forcing it.")
    assert _PERSONALIZE_HEADING in out


def test_inject_is_idempotent():
    once = _inject_personalize(f"# Skill\n\n{_SCOPE}")
    twice = _inject_personalize(once)
    assert once == twice
    assert twice.count(_PERSONALIZE_HEADING) == 1


def test_widen_arg_hint_adds_cue():
    out = _widen_arg_hint('argument-hint: [topic, chapter number, or "review <path>"]\n')
    assert 'or "<topic> in <stack>"' in out


def test_widen_arg_hint_idempotent_and_skips_non_bracket():
    already = 'argument-hint: [topic in <stack>]\n'
    assert _widen_arg_hint(already) == already  # "stack" already present
    non_bracket = 'argument-hint: "<topic> | review <path>"\n'
    assert _widen_arg_hint(non_bracket) == non_bracket  # not [..] form → untouched


def _make_skill(tmp_path: Path, *, reviewable: bool) -> Path:
    skill = tmp_path / "demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        'argument-hint: [topic, or "review <path>"]\n\n# Demo\n\n---\n\n' + _SCOPE,
        encoding="utf-8",
    )
    (skill / ".book-to-skill.json").write_text(
        json.dumps({"generator_version": "1.3.0", "reviewable": reviewable})
    )
    return skill


def test_transform_personalizes_reviewable_skill(tmp_path: Path):
    skill = _make_skill(tmp_path, reviewable=True)
    changed = _personalize_transform(skill, skill / ".source")
    assert changed == ["SKILL.md"]
    text = (skill / "SKILL.md").read_text()
    assert _PERSONALIZE_HEADING in text
    assert 'or "<topic> in <stack>"' in text
    assert json.loads((skill / ".book-to-skill.json").read_text())["personalizable"] is True


def test_transform_skips_non_code_skill(tmp_path: Path):
    skill = _make_skill(tmp_path, reviewable=False)
    changed = _personalize_transform(skill, skill / ".source")
    assert changed == []
    assert _PERSONALIZE_HEADING not in (skill / "SKILL.md").read_text()
    assert json.loads((skill / ".book-to-skill.json").read_text())["personalizable"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
