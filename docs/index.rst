book-to-skill
=============

``book-to-skill`` turns a technical book or document (PDF, EPUB, DOCX, HTML, RTF,
MOBI, Markdown) into a Claude Code skill. The ``bookextract`` package is the
extraction core: it picks the best available extractor per format, follows a
fallback chain, and writes ``full_text.txt`` plus a ``metadata.json`` summary.

This site documents the package internals — its layered architecture and the
public API of every module.

.. toctree::
   :maxdepth: 2
   :caption: Contents

   architecture
   api

Indices
-------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
