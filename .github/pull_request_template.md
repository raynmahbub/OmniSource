<!--
  Thanks for contributing to OmniSource. Keep the description short and the
  checklist honest — the CI gate (`make check`) runs the same steps.
-->

## What does this change?

<!-- One or two sentences. Link any related issue: Fixes #… -->

## Type of change

- [ ] New app or source (`catalog.json`)
- [ ] Fix for a broken upstream / dead download
- [ ] Pipeline, validation or workflow change (`src/`, `scripts/`, `.github/`)
- [ ] Website or design system (`index.html`, `assets/design-system/`, `web/`)
- [ ] Documentation

## Checklist

- [ ] I only hand-edited `catalog.json`, `assets/`, `src/`, `scripts/`, `web/` or docs — generated files were regenerated, not edited
- [ ] I ran `python3 scripts/omnisource.py --no-sync --no-health` (or a full sync) and committed the regenerated output
- [ ] `python3 scripts/validate.py` reports zero errors and `python3 -m unittest discover -s tests` passes
- [ ] No credentials, tokens, private URLs or binaries in the diff

## Notes for reviewers

<!-- Anything non-obvious: upstream quirks, tag formats, compatibility caveats, screenshots for UI changes. -->
