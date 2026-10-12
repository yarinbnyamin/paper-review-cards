#!/bin/bash
# Rebuild docs/thread.png and docs/conversation.png from examples/demo.tex.
# Needs Google Chrome (headless) and Pillow (for cropping). Run from anywhere.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
PY="${PY:-python3}"
PORT=8799
TMP="$(mktemp -d)"
cp "$ROOT/examples/demo.tex" "$TMP/main.tex"
python3 "$ROOT/server.py" --tex "$TMP/main.tex" --port $PORT >/dev/null 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null; rm -rf "$TMP"' EXIT
sleep 1

ids=$(cd "$ROOT" && python3 -c "
import scan; ts = scan.threads(open('$TMP/main.tex').read())
print(ts[0]['id'], ts[1]['id'])")
T1=${ids% *}; T2=${ids#* }

# card 2: the user asks, Claude edits the paper and answers
curl -s -X POST localhost:$PORT/api/done -H 'Content-Type: application/json' \
  -d "{\"id\":\"$T2\",\"rev\":0,\"decision\":\"change\",\"instruction\":\"Check the training script and say how the number of epochs is chosen.\"}" >/dev/null
(cd "$ROOT" && REVIEW_CARDS_DATA="$TMP/.review-cards" python3 -c "
import review_lib as R
R.propose('$T2', 'The policy is trained for 50 epochs on the demonstrations.',
          'The policy is trained on the demonstrations until its training accuracy stops improving for 5 epochs, and for at most 50 epochs; there is no separate validation split.')
R.reply('$T2', 'The training script stops after 5 epochs without improvement in training accuracy, capped at 50, and uses no validation set. The sentence now says so.')
R.set_status('$T2', 'review'); R.mark_processed(len(R.queue()))")

shot() {  # url, output, height
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
    --window-size=1100,$3 --virtual-time-budget=6000 --screenshot="$2" "$1" >/dev/null 2>&1
}
shot "http://localhost:$PORT/#$T1" "$ROOT/docs/thread.png" 1500
shot "http://localhost:$PORT/#$T2" "$ROOT/docs/conversation.png" 1500

# trim the empty page background below the card
$PY - "$ROOT/docs/thread.png" "$ROOT/docs/conversation.png" <<'EOF'
import sys
from PIL import Image
for f in sys.argv[1:]:
    im = Image.open(f).convert("RGB"); W, H = im.size; bg = im.getpixel((5, H - 5)); y = H - 1
    while y > 0 and all(im.getpixel((x, y)) == bg for x in range(0, W, 20)):
        y -= 1
    im.crop((0, 0, W, min(H, y + 40))).save(f, optimize=True)
    print(f, "->", min(H, y + 40))
EOF
