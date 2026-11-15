# Experimental workspaces and rollback

The dashboard now offers five query-addressed views:

- `?page=home`: Navigation shortcuts.
- `?page=map`: maps, samples, layers and the 3D terrain window.
- `?page=stories`: investigations, evidence, tours and sonification.
- `?page=review`: candidate review queue.
- `?page=data`: findings, archive, methods and links to research/candidate pages.

The same map and measured-data state is kept while switching views. Existing
site/sample/case links infer the appropriate view. Investigation links reveal
the view that owns their target window. Browser back/forward works with the query URLs.
Map layers collapse behind a button on small screens. Motion respects
`prefers-reduced-motion`.

## Immediate rollback

Use **Classic overview** in the navigation, or open `?layout=classic`. This restores
the original overview without reloading or clearing measurements and language.
Use **Use workspaces** or `?layout=workspaces` to switch back. The layout choice is
stored in `offbeat.layout.v1`; the language remains in `offbeat.language.v1`.

## Archived assistant version

The assistant module has been removed from the active UI and API. The version with
the assistant was archived locally before removal. Its local Git tag starts with
`archive/with-llm-`. That historical snapshot includes the assistant; use the
Classic overview toggle to compare layouts without restoring the assistant.
