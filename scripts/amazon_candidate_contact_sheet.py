"""Render a reproducible inspection sheet from already prepared optical previews."""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
receipt = json.loads((ROOT / 'data/analysis/amazon-candidate-visual-check-2026-11-15.json').read_text(encoding='utf-8'))
radar_path = ROOT / receipt['radar_source']
assert hashlib.sha256(radar_path.read_bytes()).hexdigest() == receipt['radar_source_sha256']
radar = json.loads(radar_path.read_text(encoding='utf-8'))
images = []
for item in receipt['optical_images']:
    path = ROOT / item['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
    images.append(Image.open(path).convert('RGBA'))
b = radar['bbox']
sheet = Image.new('RGB', (630, 225 * len(radar['markers'])), 'white')
draw = ImageDraw.Draw(sheet)
for row, marker in enumerate(radar['markers']):
    for col, img in enumerate(images):
        x = round((marker['lon'] - b['w']) / (b['e'] - b['w']) * img.width)
        y = round((b['n'] - marker['lat']) / (b['n'] - b['s']) * img.height)
        tile = img.crop((x - 32, y - 32, x + 32, y + 32))
        back = Image.new('RGBA', tile.size, (90, 90, 90, 255))
        back.alpha_composite(tile)
        sheet.paste(back.convert('RGB').resize((192, 192), Image.Resampling.NEAREST), (col * 210, row * 225 + 23))
        cx, cy = col * 210 + 96, row * 225 + 119
        draw.line((cx - 6, cy, cx + 6, cy), fill='yellow')
        draw.line((cx, cy - 6, cx, cy + 6), fill='yellow')
        draw.text((col * 210 + 3, row * 225 + 2), f"{marker['id']} / {receipt['optical_images'][col]['date']}", fill='black')
out = ROOT / '.work-audit' / 'amazon-visual-review.png'
out.parent.mkdir(exist_ok=True)
sheet.save(out)
print(out)
