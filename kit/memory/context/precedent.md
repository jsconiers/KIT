# Precedent setup

What the precedent finder and `kit-precedent` use. They read this before every job, so keep it
current.

- **Sources:** these files and folders in the library root (see `library.md`), unless you set
  others here. `kit-precedent` searches the files listed and the markdown files directly inside
  the folders listed. Add a published library's index by its path in the library root.
  - `CATALOG.md`
  - `LOG.md`
  - `knowledge/`
  - `decisions/INDEX.md`
  - `poc/INDEX.md`
  - `labs/REGISTER.md`
  - `radar/`
  - `published/`
- **Extra sources:** optional. Index files or folders outside the library root, by full path, one
  per line, like the list above.
- **Current means:** decided, published, or tested within 36 months, and not superseded. Older
  precedents are reported as "old", not dropped. Change the number here.
- **Ranking:** exact match, then same system, then same pattern, then related. Within a rank,
  current before old, and decisions and published documents before drafts.
- **Notes:** `<library root>/artifacts/<project>/precedent/`, written only when Kit asks.
- **Reference architectures:** not set. Where the team's reference architectures live. Only these
  and the standards in `standards.md` count as standards; everything else is precedent.
