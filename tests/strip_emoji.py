"""Strip remaining emoji from topbar and label strings in desktop.py."""
import re
import os

f = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "eonix-desktop", "desktop.py")

with open(f, "r", encoding="utf-8") as fp:
    c = fp.read()

# Fix topbar labels
c = c.replace("\u26a1 EONIX |", "* EONIX |")
c = c.replace("\u2b50 EONIX |", "* EONIX |")

EMOJI_RE = re.compile(
    "["
    "\U00010000-\U0010ffff"
    "\u2600-\u27bf"
    "\u2300-\u23ff"
    "\ufe0e\ufe0f"
    "\u200d"
    "]+", re.UNICODE)

lines = c.split("\n")
new_lines = []
for line in lines:
    if "EONIX |" in line and EMOJI_RE.search(line):
        cleaned = EMOJI_RE.sub("*", line)
        new_lines.append(cleaned)
    elif "label=" in line and EMOJI_RE.search(line):
        cleaned = EMOJI_RE.sub("", line)
        cleaned = re.sub(r'label="\s+', 'label="', cleaned)
        new_lines.append(cleaned)
    else:
        new_lines.append(line)

with open(f, "w", encoding="utf-8") as fp:
    fp.write("\n".join(new_lines))

# Verify
with open(f, "r", encoding="utf-8") as fp:
    c2 = fp.read()
emoji_label = [l.strip() for l in c2.split("\n") if "label=" in l and EMOJI_RE.search(l)]
print(f"Labels with emoji remaining: {len(emoji_label)}")
for l in emoji_label[:5]:
    print(f"  {l}")
if not emoji_label:
    print("All clean!")
