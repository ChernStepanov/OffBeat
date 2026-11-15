# Groq workspace copilot

The start page includes a Win98 chat window, a draggable floating mode and a
fullscreen mode. The configured server-side model is `openai/gpt-oss-20b`.

Local setup (Python standard library, no new packages):

```sh
# Put GROQ_API_KEY=your-key in the ignored .env file, or export it in the server environment.
python3 -m api.dev_server --port 8877
```

Open http://127.0.0.1:8877/ . A static-only HTTP server/GitHub Pages cannot
provide chat; deployment needs the `/api/v1/copilot` route on the same origin.
Keep credentials on the server. The local integrated server denies dotfiles
including encoded `.env` and `.git` paths for GET and HEAD. Do not serve this
checkout with an unrestricted static server while it contains a credential.

`POST /api/v1/copilot` accepts bounded user/assistant/tool messages and selected
site/sample context. It injects its own system instructions and selected real
measurements from repository data, fixes the model and upstream URL, and strips
reasoning fields. API keys and upstream error bodies are never sent to clients.
The local server listens on loopback; public deployment additionally needs its
own authentication and usage limits.

Tools use a scoped `workspace` function, executed in the browser, with actual
success/error results returned to the model before it describes completion:

- `place`: resolve a name or coordinates; clear unrelated sample data; fly to a
  suitable zoom (country/city/neighbourhood). Named geocoding depends on the
  existing geocoding services. Uncovered locations only have context imagery.
- `site`, `inspect`: select prepared data or samples, return actual measured
  arrays, dates, source and ranked sample references.
- `window`: open map, terrain, evidence, review, pixel charts or chat; maximize
  or restore panels when supported by the existing window manager.
- `settings`: change valid acquisition date, threshold 1.5–6, HH/HV and
  offbeat/cover layers. Invalid dates/channels/indices are rejected.
- `chart`: line/bar/histogram from measured HH/HV only; missing observations
  stay missing. Line charts position observations by acquisition date.
- `play`: existing measured sample sonification.

No arbitrary JavaScript, shell commands, files or messages are executable.
This is a workspace assistant, not unrestricted computer control. A request
executes at most six actions and seven model rounds. Stop aborts model requests;
pending geocoding results are checked before navigation. Completed actions
are not undone. Enter sends; Shift+Enter adds a line. Escape exits fullscreen.
Animations respect reduced-motion preferences. Chats live in page memory.

The assistant does not establish physical causes or independently validated
accuracy. It can explain measurements, coverage and uncertainty, but cannot
turn a radar anomaly into a verified event or invent absent measurements.

Verification: live Groq tool loop opened Amazon and produced an actual measured
HV chart; Chrome exercised settings, 3D, fullscreen and 390px layout. Unit tests
cover fixed model, server-grounded facts, bounded roles/history, missing config,
and provider-error redaction:

```sh
python3 -m unittest api.test_copilot -v
node scripts/test_navigation.mjs
node scripts/test_evidence.mjs
node scripts/version_assets.mjs --check
```

Provider reference: https://console.groq.com/docs/tool-use/overview and
https://console.groq.com/docs/api-reference .
