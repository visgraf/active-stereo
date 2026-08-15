# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Tags mark milestones and submissions, so the paper can cite a fixed state.

## [Unreleased]

### Added
- Six-layer package structure (`geometry`, `encoding`, `inference`, `scaling`,
  `control`, `policy`) with Protocol-based extension points (ADR-0004)
- `Estimate` type carrying value and variance (ADR-0005)
- `RunContext`: run-ids pinned to git SHA, seed, and config
- Five seed ADRs; three backed by regression tests
- CI: tests on 3.10/3.12, lint, types, and a separate ADR-regression job
- `CLAUDE.md` constitution, scoped permissions, four custom commands

### Fixed
- Parabolic subpixel fit produced variance 0 alongside a `nan` location when a
  neighbouring cost was infinite — a maximally confident non-answer
- Eccentricity normalisation was off by half a pixel, making the ADR-0003
  penalty resolution-dependent at the 3% level

### Migration status
- `encoding`: Protocol only; energy model not yet migrated
- `inference`: block matching and SGBM; MRF belief propagation pending
- `scripts`: Blender render scripts pending
