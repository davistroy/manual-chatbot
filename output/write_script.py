
import pathlib

out = pathlib.Path("C:/Users/Troy Davis/dev/personal/manual-chatbot/output/validate_cj.py")

lines = []
def L(s):
    lines.append(s)

L("import sys")
L("import traceback")
L("import statistics")
L("from collections import Counter")
L("")
L("sys.path.insert(0, 'C:/Users/Troy Davis/dev/personal/manual-chatbot/src')")
L("")
L("PROF = 'C:/Users/Troy Davis/dev/personal/manual-chatbot/tests/fixtures/cj_universal_profile.yaml'")
L("PDF = 'C:/Users/Troy Davis/dev/personal/manual-chatbot/data/53-71 CJ5 Service Manual.pdf'")
L("")

out.write_text(chr(10).join(lines), encoding="utf-8")
print(f"Written {len(lines)} lines")
