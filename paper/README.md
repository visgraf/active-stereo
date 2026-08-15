# Paper

Synced with Overleaf through its **Git bridge**. Treat this repository as
canonical and Overleaf as the co-author editing surface.

## Setup

1. In Overleaf, open the project menu and copy the Git URL (a paid-tier feature).
2. Add it as a remote and sync `paper/` only — a subtree or a separate clone,
   depending on how much of the repo your co-authors should see.
3. Pull from Overleaf before editing `paper/` locally; the bridge is a sync
   point, not a merge engine.

If the Overleaf tier is a blocker, keep LaTeX here and build with
`latexmk -pdf -cd paper/main.tex`. CI compiles the PDF on every push touching
`paper/`, so a broken build is caught immediately either way.

## Conventions

- **One sentence per line.** Git diffs become readable and merges become
  tractable. This matters more than it sounds.
- Every number in §Experiments cites a **run-id** from `experiments/*/findings.md`.
- Cite the code by **tag**, never by branch.
- Append to `refs.bib`; never rewrite it wholesale.
