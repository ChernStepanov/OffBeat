# Experimental workspaces and rollback

The dashboard now offers five query-addressed views:

- `?page=home`: Copilot and shortcuts.
- `?page=map`: maps, samples, layers and the 3D terrain window.
- `?page=stories`: investigations, evidence, tours and sonification.
- `?page=review`: candidate review queue.
- `?page=data`: findings, archive, methods and links to research/candidate pages.

The same map and measured-data state is kept while switching views. Existing
site/sample/case links infer the appropriate view. Copilot tools reveal the view
that owns their target window. Browser back/forward works with the query URLs.
Map layers collapse behind a button on small screens; floating mobile chat can be
expanded from its title bar. Motion respects `prefers-reduced-motion`.

## Immediate rollback

Use **Classic overview** in the navigation, or open `?layout=classic`. This restores
the original overview without reloading or clearing measurements and language.
Use **Use workspaces** or `?layout=workspaces` to switch back. The layout choice is
stored in `offbeat.layout.v1`; the language remains in `offbeat.language.v1`.

## Code rollback

Language support is committed before the workspace experiment and marked by
`checkpoint/i18n-before-workspaces`. The `feature/persistent-languages` branch
points to that checkpoint. Revert the subsequent workspace commit to remove the
experiment while retaining permanent languages and Copilot's language context.
Do not reset another checkout containing local work. The classic toggle is the
preferred way to compare layouts before deciding whether to keep the experiment.
