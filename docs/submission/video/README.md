# OffBeat presentation video (29.6 s)

`../offbeat-video.webm` (VP9 + Opus, 3.7 MB, played first on the site) and `../offbeat-video.mp4` (H.264 + AAC, 5.9 MB, fallback and download): 1920x1080, 30 fps, under the 30-second Space Apps limit. `../offbeat-video-poster.jpg` is shown before playback.

Everything on screen comes from the running app or measured data: map stills are screenshots of
OffBeat, the chart is NISAR sample MEX r8 c2, the numbers come from `data/findings.json`. The music
is synthesised; its melodic line in the pixel-card scene is the sonification of MEX r8 c2 with the
mapping in `js/sonify.js`.

Rebuild (needs Node, `puppeteer-core`, Chromium, ffmpeg and the repository's `.venv`):

1. Serve the repository on port 8765 and run `node capture.js` (writes `stills/`).
2. From the repository root: `.venv/bin/python docs/submission/video/export_data.py` (writes `data.js`).
3. Link `css/` and `fonts/` from the repository next to `index.html`, serve this folder on 8766.
4. `node render.js frames` (deterministic frames), `python synth.py` (soundtrack.wav).
5. Encode:
   - `ffmpeg -framerate 30 -i frames/f%04d.jpg -i soundtrack.wav -c:v libvpx-vp9 -crf 42 -b:v 0 -deadline good -cpu-used 2 -row-mt 1 -tile-columns 2 -pix_fmt yuv420p -c:a libopus -b:a 96k -shortest offbeat-video.webm`
   - `ffmpeg -framerate 30 -i frames/f%04d.jpg -i soundtrack.wav -c:v libopenh264 -b:v 2M -maxrate 3M -g 60 -pix_fmt yuv420p -c:a aac -b:a 128k -shortest -movflags +faststart offbeat-video.mp4`
   - `ffmpeg -ss 2.4 -i offbeat-video.webm -frames:v 1 -q:v 3 offbeat-video-poster.jpg`
