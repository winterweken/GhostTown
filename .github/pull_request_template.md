## Summary

<!-- What does this change, and why? One or two sentences. -->

## What changed

-

## Testing

- [ ] `uv run pytest` passes (fetcher tests; they run offline)
- [ ] Blender tests pass: `blender --background --factory-startup --python-exit-code 1 --python tests/blender/run.py`
- [ ] For data, geometry or panel changes: built a live site and looked at the result. Site and radius:

## Checklist

- [ ] New behaviour has a test that failed before the change
- [ ] Tests don't touch the network (recorded answers go in `tests/fetch/fixtures/`)
- [ ] A new data source is credited, with its licence, in `CREDITS.md` and the README
- [ ] Nothing in `ghosttown_fetch/` imports `bpy`, and the Blender side doesn't import shapely
- [ ] Text people read says "Ghost Town"
- [ ] No personal paths, keys or private data in code, fixtures or screenshots

## Notes for the reviewer

<!-- Anything that needs a careful look, decisions you made, or follow-ups you left out. -->
