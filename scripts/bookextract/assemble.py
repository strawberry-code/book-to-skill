"""Deterministic assembler: validated notes → an OKF v0.1 bundle.

This is the half of the orchestrated build that the *code* owns (the agent only
emits Note JSON). It grounds every citation, deduplicates notes by slug across
chunks, **inserts reciprocal ``## Related`` backlinks**, computes printed folios,
and writes every OKF file (notes, section/root ``index.md``, ``references/``,
``moc/``, ``log.md``, ``.mycelia.json``) — then runs ``okf_lint`` as the gate.
Moving links/folios/dedup here is what removes the drift of hand-emission.

Scope: one source per call (rebuilds the bundle from the full note set, so re-runs
are idempotent). Multi-book incremental assembly is a roadmap item.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from bookextract import __version__
from bookextract.notes import (
    GroundedCitation,
    NormalizedSource,
    Note,
    NoteValidationError,
    ground_with_source,
    normalized_source,
)
from bookextract.okf_lint import LintReport, lint_bundle
from bookextract.reconcile import reconcile_slugs

_TYPE_DIR: Final[dict[str, str]] = {
    "Concept": "concepts",
    "Framework": "frameworks",
    "Principle": "principles",
    "Entity": "entities",
    "Method": "methods",
    "AntiPattern": "anti-patterns",
}
_SECTION_ORDER: Final[tuple[str, ...]] = (
    "concepts",
    "frameworks",
    "principles",
    "entities",
    "methods",
    "anti-patterns",
)
_OKF_VERSION: Final[str] = "0.1"


@dataclass(frozen=True)
class Source:
    """Provenance for the one book being assembled into the bundle."""

    slug: str
    title: str
    authors: tuple[str, ...]
    extraction_method: str
    source_sha256: str
    source_filename: str
    raw_rel: str
    page_offset: int | None


@dataclass(frozen=True)
class SourceDoc:
    """One book's provenance paired with its immutable raw text (for grounding)."""

    source: Source
    raw_text: str


@dataclass(frozen=True)
class AssembleInputs:
    """Everything the assembler needs to build one bundle from one or more books."""

    notes: list[Note]
    sources: tuple[SourceDoc, ...]
    timestamp: str

    @classmethod
    def single(
        cls, notes: list[Note], source: Source, raw_text: str, timestamp: str
    ) -> AssembleInputs:
        """Convenience constructor for the common single-book case."""
        return cls(notes=notes, sources=(SourceDoc(source, raw_text),), timestamp=timestamp)


@dataclass
class _DropStats:
    """What ``_collect`` discarded so the assembler can report it (never silently)."""

    citations: int = 0  # ungroundable citations skipped
    notes: int = 0  # notes dropped for having no groundable citation left


@dataclass
class _Merged:
    """A note accumulated across chunks (mutable: merges and backlinks land here)."""

    type: str
    slug: str
    title: str
    description: str
    confidence: str
    status: str
    tags: list[str]
    aliases: list[str]
    body: str
    related: set[str]
    citations: list[GroundedCitation]
    merged: bool = False


@dataclass(frozen=True)
class _Ctx:
    """Render-time lookups shared across the writers."""

    timestamp: str
    sources: dict[str, Source]
    slug_index: dict[str, tuple[str, str, str]]  # slug -> (dir, title, description)


def _union(base: list[str], extra: tuple[str, ...]) -> list[str]:
    """Order-preserving union of two string sequences."""
    out = list(base)
    for item in extra:
        if item not in out:
            out.append(item)
    return out


def _norm_key(value: str) -> str:
    """Casefolded key for slug/alias matching."""
    return value.strip().casefold()


def _ground_all(
    note: Note, docs: dict[str, SourceDoc], norms: dict[str, NormalizedSource]
) -> tuple[list[GroundedCitation], int]:
    """Ground a note's citations against each one's (precomputed) source; skip/count failures.

    Each citation names its source slug, so cross-book notes ground every quote against
    the right book's raw text — reusing that book's precomputed normalized index. A
    citation whose source is unknown, or whose near-verbatim quote fails the exact check,
    is dropped and reported rather than raised — one bad citation must not abort the bundle.
    """
    grounded: list[GroundedCitation] = []
    dropped = 0
    for citation in note.citations:
        doc, norm = docs.get(citation.source), norms.get(citation.source)
        if doc is None or norm is None:
            dropped += 1
            continue
        try:
            grounded.append(ground_with_source(citation, norm, doc.source.page_offset))
        except NoteValidationError:
            dropped += 1
    return grounded, dropped


def _new(note: Note, grounded: list[GroundedCitation], slug: str) -> _Merged:
    """Build a fresh accumulator from a note's first occurrence under ``slug``."""
    return _Merged(
        type=note.type,
        slug=slug,
        title=note.title,
        description=note.description,
        confidence=note.confidence,
        status=note.status,
        tags=list(note.tags),
        aliases=list(note.aliases),
        body=note.body,
        related=set(note.related),
        citations=list(grounded),
    )


def _merge(dst: _Merged, note: Note, grounded: list[GroundedCitation], *, primary: bool) -> None:
    """Fold a repeat occurrence into its canonical accumulator.

    ``primary`` is true when this occurrence's own slug is the canonical one, so
    its identity fields win regardless of chunk order (the acronym occurrence
    must not impose its title on the spelled-out canonical note).
    """
    dst.tags = _union(dst.tags, note.tags)
    dst.aliases = _union(dst.aliases, note.aliases)
    dst.related |= set(note.related)
    seen = {(c.source, c.chapter, c.quote) for c in dst.citations}
    for cit in grounded:
        if (cit.source, cit.chapter, cit.quote) not in seen:
            dst.citations.append(cit)
            seen.add((cit.source, cit.chapter, cit.quote))
    if primary:
        dst.type, dst.title, dst.description = note.type, note.title, note.description
        dst.confidence, dst.status = note.confidence, note.status
    elif not dst.description:
        dst.description = note.description
    if len(note.body) > len(dst.body):
        dst.body = note.body
    dst.merged = True


def _collect(
    notes: list[Note], docs: dict[str, SourceDoc]
) -> tuple[dict[str, _Merged], _DropStats]:
    """Deduplicate notes by canonical slug, grounding each citation as it folds in.

    Beyond exact-slug dedup, :func:`reconcile_slugs` folds acronym/plural variants
    into one canonical note; the folded slug is recorded as an alias so ``related``
    links resolve through the existing alias index. Notes sharing a slug across books
    merge into one canonical note that accrues citations from every source. Ungroundable
    citations are skipped, and a note left with no groundable citation is dropped (it
    could not satisfy the coverage gate anyway) — both are counted in the returned stats.
    """
    remap = reconcile_slugs({n.slug for n in notes})
    norms = {slug: normalized_source(doc.raw_text) for slug, doc in docs.items()}  # once per book
    canon: dict[str, _Merged] = {}
    stats = _DropStats()
    for note in notes:
        grounded, dropped = _ground_all(note, docs, norms)
        stats.citations += dropped
        if not grounded:
            stats.notes += 1
            continue
        target = remap.get(note.slug, note.slug)
        if target in canon:
            _merge(canon[target], note, grounded, primary=note.slug == target)
        else:
            canon[target] = _new(note, grounded, target)
        if note.slug != target:
            canon[target].aliases = _union(canon[target].aliases, (note.slug,))
    return canon, stats


def _alias_index(canon: dict[str, _Merged]) -> dict[str, str]:
    """Map slug + alias keys to the canonical slug that owns them."""
    index: dict[str, str] = {}
    for slug, merged in canon.items():
        index[_norm_key(slug)] = slug
        for alias in merged.aliases:
            index.setdefault(_norm_key(alias), slug)
    return index


def _resolve_related(canon: dict[str, _Merged], index: dict[str, str]) -> None:
    """Resolve related slugs to canonical notes and insert reciprocal backlinks."""
    for merged in canon.values():
        resolved = {
            target
            for raw_slug in merged.related
            if (target := index.get(_norm_key(raw_slug))) and target != merged.slug
        }
        merged.related = resolved
    for slug, merged in list(canon.items()):
        for target in list(merged.related):
            if target in canon:
                canon[target].related.add(slug)


def _yaml(value: str) -> str:
    """A safely double-quoted YAML scalar (JSON encoding is valid YAML)."""
    return json.dumps(value, ensure_ascii=False)


def _frontmatter(merged: _Merged, timestamp: str) -> list[str]:
    """The OKF frontmatter block (recommended fields + governance extensions)."""
    lines = [
        "---",
        f"type: {merged.type}",
        f"title: {_yaml(merged.title)}",
        f"description: {_yaml(merged.description)}",
        f"tags: [{', '.join(merged.tags)}]",
        f"timestamp: {timestamp}",
    ]
    if merged.merged:
        lines.append(f"updated: {timestamp}")
    if merged.aliases:
        lines.append(f"aliases: [{', '.join(merged.aliases)}]")
    lines += [
        f"confidence: {merged.confidence}",
        "contested: false",
        f"status: {merged.status}",
        "---",
    ]
    return lines


def _render_related(merged: _Merged, ctx: _Ctx) -> list[str]:
    """The ``## Related`` section (bundle-relative links to canonical notes)."""
    if not merged.related:
        return []
    lines = ["## Related"]
    for slug in sorted(merged.related):
        info = ctx.slug_index.get(slug)
        if info is not None:
            directory, title, description = info
            lines.append(f"- [{title}](/{directory}/{slug}.md) — {description}")
    return [*lines, ""]


def _render_citations(merged: _Merged, ctx: _Ctx) -> list[str]:
    """The numbered ``# Citations`` section grounded against the source."""
    lines = ["# Citations"]
    for num, cit in enumerate(merged.citations, 1):
        ref = f"[Ch {cit.chapter}, p.{cit.folio}]" if cit.folio else f"[Ch {cit.chapter}]"
        src = ctx.sources.get(cit.source)
        title = src.title if src is not None else cit.source
        lines.append(f'[{num}] {ref} "{cit.quote}" — [{title}](/references/{cit.source}.md)')
    return lines


def _render_note(merged: _Merged, ctx: _Ctx) -> str:
    """Render a full atomic-note Markdown file."""
    parts = [
        *_frontmatter(merged, ctx.timestamp),
        "",
        f"# {merged.title}",
        "",
        merged.body.strip(),
        "",
        *_render_related(merged, ctx),
        *_render_citations(merged, ctx),
    ]
    return "\n".join(parts).rstrip() + "\n"


def _write(path: Path, text: str) -> None:
    """Write text, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_notes(bundle: Path, canon: dict[str, _Merged], ctx: _Ctx) -> None:
    """Write every atomic-note file under its type directory."""
    for merged in canon.values():
        directory = _TYPE_DIR[merged.type]
        _write(bundle / directory / f"{merged.slug}.md", _render_note(merged, ctx))


def _section_index(bundle: Path, directory: str, canon: dict[str, _Merged], ctx: _Ctx) -> None:
    """Write a frontmatter-free section ``index.md`` listing its notes."""
    slugs = sorted(s for s, m in canon.items() if _TYPE_DIR[m.type] == directory)
    if not slugs:
        return
    lines = [f"# {directory.replace('-', ' ').title()}", ""]
    for slug in slugs:
        _, title, description = ctx.slug_index[slug]
        lines.append(f"- [{title}](/{directory}/{slug}.md) — {description}")
    _write(bundle / directory / "index.md", "\n".join(lines) + "\n")


def _notes_for_source(canon: dict[str, _Merged], slug: str) -> dict[str, _Merged]:
    """The subset of notes carrying at least one citation from ``slug``'s book."""
    return {s: m for s, m in canon.items() if any(c.source == slug for c in m.citations)}


def _write_indexes(
    bundle: Path, canon: dict[str, _Merged], ctx: _Ctx, sources: tuple[Source, ...]
) -> None:
    """Write per-section, references, and moc ``index.md`` files (no frontmatter)."""
    for directory in _SECTION_ORDER:
        _section_index(bundle, directory, canon, ctx)
    refs = [f"- [{s.title}](/references/{s.slug}.md) — {', '.join(s.authors)}" for s in sources]
    _write(bundle / "references" / "index.md", "# References\n\n" + "\n".join(refs) + "\n")
    mocs = [f"- [{s.title}](/moc/{s.slug}.md) — every note sourced from the book" for s in sources]
    _write(bundle / "moc" / "index.md", "# Maps of content\n\n" + "\n".join(mocs) + "\n")


def _write_source(bundle: Path, source: Source, ctx: _Ctx) -> None:
    """Write the ``type: Source`` provenance note for the book."""
    parts = [
        "---",
        "type: Source",
        f"title: {_yaml(source.title)}",
        f"description: {_yaml(', '.join(source.authors))}",
        "tags: [source]",
        f"timestamp: {ctx.timestamp}",
        f"extraction_method: {source.extraction_method}",
        f"source_sha256: {source.source_sha256}",
        f"raw: /{source.raw_rel}",
        "---",
        "",
        f"# {source.title}",
        "",
        f"**Author(s):** {', '.join(source.authors)} · "
        f"**Extraction:** {source.extraction_method}",
        "",
        f"See its [map of content](/moc/{source.slug}.md).",
        "",
        "# Citations",
        "<!-- this note IS the source; no external citations -->",
    ]
    _write(bundle / "references" / f"{source.slug}.md", "\n".join(parts) + "\n")


def _write_moc(bundle: Path, source: Source, canon: dict[str, _Merged], ctx: _Ctx) -> None:
    """Write a book's map-of-content over the notes that cite it, grouped by type."""
    own = _notes_for_source(canon, source.slug)
    parts = [
        "---",
        "type: MOC",
        f"title: {_yaml(source.title + ' — map of content')}",
        f"description: {_yaml('Navigation hub for ' + source.title)}",
        "tags: [moc]",
        f"timestamp: {ctx.timestamp}",
        f"source: /references/{source.slug}.md",
        "---",
        "",
        f"# {source.title} — Map of Content",
    ]
    for directory in _SECTION_ORDER:
        slugs = sorted(s for s, m in own.items() if _TYPE_DIR[m.type] == directory)
        if not slugs:
            continue
        parts += ["", f"## {directory.replace('-', ' ').title()}"]
        parts += [f"- [{ctx.slug_index[s][1]}](/{directory}/{s}.md)" for s in slugs]
    _write(bundle / "moc" / f"{source.slug}.md", "\n".join(parts) + "\n")


def _vault_title(sources: tuple[Source, ...]) -> str:
    """Bundle title: the book's title for one source, else a corpus label."""
    if len(sources) == 1:
        return f"{sources[0].title} — Mycelia Vault"
    return f"Mycelia Vault — {len(sources)} sources"


def _write_root_index(bundle: Path, sources: tuple[Source, ...], canon: dict[str, _Merged]) -> None:
    """Write the bundle-root ``index.md`` (the only index that may carry okf_version)."""
    lines = [
        "---",
        f'okf_version: "{_OKF_VERSION}"',
        "---",
        "",
        f"# {_vault_title(sources)}",
        "",
        "An atomic, interlinked OKF knowledge vault generated by Mycelia.",
        "",
        "## Sections",
    ]
    for directory in _SECTION_ORDER:
        if any(_TYPE_DIR[m.type] == directory for m in canon.values()):
            lines.append(f"- [{directory.replace('-', ' ').title()}](/{directory}/index.md)")
    lines += ["- [References](/references/index.md)", "- [Maps of content](/moc/index.md)"]
    lines += ["", "## Sources"]
    lines += [f"- [{s.title}](/references/{s.slug}.md) — {', '.join(s.authors)}" for s in sources]
    _write(bundle / "index.md", "\n".join(lines) + "\n")


def _write_log(bundle: Path, canon: dict[str, _Merged], ctx: _Ctx, stats: _DropStats) -> None:
    """Write ``log.md`` with a single dated ingest entry (idempotent rebuild)."""
    sources = tuple(ctx.sources.values())
    merged = sum(1 for m in canon.values() if m.merged)
    label = f'"{sources[0].title}"' if len(sources) == 1 else f"{len(sources)} sources"
    dropped = ""
    if stats.citations or stats.notes:
        dropped = (
            f" Dropped {stats.citations} ungroundable citation(s) "
            f"and {stats.notes} uncited note(s)."
        )
    entry = (
        f"- **Create** Assembled {len(canon)} atomic notes from "
        f"{label} ({merged} merged across sources/chunks).{dropped}"
    )
    _write(bundle / "log.md", f"# Log\n\n## {ctx.timestamp[:10]}\n{entry}\n")


def _write_manifest(bundle: Path, canon: dict[str, _Merged], ctx: _Ctx, stats: _DropStats) -> None:
    """Write ``.mycelia.json`` provenance + per-section note counts."""
    day = ctx.timestamp[:10]
    counts = {
        directory: sum(1 for m in canon.values() if _TYPE_DIR[m.type] == directory)
        for directory in _SECTION_ORDER
    }
    manifest = {
        "generator_version": __version__,
        "okf_version": _OKF_VERSION,
        "updated": day,
        "sources": [
            {
                "slug": s.slug,
                "source_filename": s.source_filename,
                "extraction_method": s.extraction_method,
                "source_sha256": s.source_sha256,
                "page_offset": s.page_offset,
                "ingested": day,
            }
            for s in ctx.sources.values()
        ],
        "note_counts": counts,
        "dropped": {"citations": stats.citations, "notes": stats.notes},
    }
    _write(bundle / ".mycelia.json", json.dumps(manifest, indent=2) + "\n")


def assemble(inputs: AssembleInputs, bundle_dir: Path) -> LintReport:
    """Assemble validated notes (from one or more books) into an OKF bundle; return the gate."""
    timestamp = inputs.timestamp
    docs = {doc.source.slug: doc for doc in inputs.sources}
    sources = tuple(doc.source for doc in inputs.sources)
    canon, stats = _collect(inputs.notes, docs)
    _resolve_related(canon, _alias_index(canon))
    slug_index = {s: (_TYPE_DIR[m.type], m.title, m.description) for s, m in canon.items()}
    ctx = _Ctx(timestamp=timestamp, sources={s.slug: s for s in sources}, slug_index=slug_index)
    _write_notes(bundle_dir, canon, ctx)
    _write_indexes(bundle_dir, canon, ctx, sources)
    for source in sources:
        _write_source(bundle_dir, source, ctx)
        _write_moc(bundle_dir, source, canon, ctx)
    _write_root_index(bundle_dir, sources, canon)
    _write_log(bundle_dir, canon, ctx, stats)
    _write_manifest(bundle_dir, canon, ctx, stats)
    return lint_bundle(bundle_dir, strict_links=True)
