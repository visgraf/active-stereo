# Data

**Pointers only. Never blobs.** Everything here is git-ignored except this file
and `.dvc` pointer files.

Rendered scenes, ground-truth depth maps, and calibration captures are tracked by
DVC (or git-lfs) and stored outside the repository. A repository that carries its
own gigabytes stops being clonable, and a research repo has a long life.

Nothing in the pipeline writes here. Outputs go to `results/`, addressed by
run-id.

## Adding a dataset

```bash
dvc add data/scenes/textured_slant
git add data/scenes/textured_slant.dvc data/.gitignore
```

Record provenance — render script, Blender version, config, date — in
`docs/lab-notebook/`. A dataset whose provenance is lost is not reproducible,
whatever the checksum says.
