Architecture
============

The package follows a **functional core / imperative shell** design. Pure logic
(structure detection, metadata assembly, install decisions, the extractor chain)
returns plain data and never performs console or file I/O. A single shell module
(:mod:`bookextract.cli`) reads ``argv``/env, prints, writes files, and exits.

Layers
------

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Module
     - Responsibility
   * - :mod:`bookextract.types`
     - Foundational primitives: the extraction-mode literal, the frozen set of
       legal extraction-method names, the typed :class:`~bookextract.types.ExtractionError`,
       and the opt-in debug logger.
   * - :mod:`bookextract.extractors`
     - The :class:`~bookextract.extractors.Extractor` Protocol plus one adapter
       per library/tool. Heavy imports stay lazy inside ``extract``.
   * - :mod:`bookextract.formats`
     - The :class:`~bookextract.formats.FormatSpec` table — the single source of
       truth binding an extension to its extractor chain, page-count strategy,
       dynamic metadata key, and dependency offers. Also magic-byte sniffing.
   * - :mod:`bookextract.pipeline`
     - :func:`~bookextract.pipeline.run_chain`, the generic
       Chain-of-Responsibility runner over a format's extractors.
   * - :mod:`bookextract.progress`
     - Optional ``rich`` progress display, driven by a page/chapter reporter
       callback; a silent no-op off a TTY or when ``rich`` is absent.
   * - :mod:`bookextract.structure`
     - Pure chapter/table-of-contents detection.
   * - :mod:`bookextract.metadata`
     - Pure ``metadata.json`` assembly.
   * - :mod:`bookextract.deps`
     - Optional-dependency discovery, the pure install **decision**, and the
       side-effecting install **flow**.
   * - :mod:`bookextract.cli`
     - The imperative shell: argument parsing, orchestration, and all I/O.

Data flow
---------

#. The shell resolves the input to a :class:`~bookextract.formats.FormatSpec`
   (by extension, or by magic-byte sniffing for mis-named files).
#. It offers any missing optional dependencies for that format.
#. :func:`~bookextract.pipeline.run_chain` tries each in-mode, available
   extractor in order and returns the first non-empty text.
#. The shell computes the page/section count, detects structure, assembles the
   metadata, writes both output files, and prints a summary.

The contract consumed by ``SKILL.md`` — CLI flags, environment variables, the two
output files, and every ``metadata.json`` field name — is held stable by the
golden tests in ``tests/test_extract.py``.
