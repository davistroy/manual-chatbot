import pathlib

SCRIPT = """
import sys, traceback, statistics
from collections import Counter

sys.path.insert(0, "C:/Users/Troy Davis/dev/personal/manual-chatbot/src")
PROF = "C:/Users/Troy Davis/dev/personal/manual-chatbot/tests/fixtures/cj_universal_profile.yaml"
PDF  = "C:/Users/Troy Davis/dev/personal/manual-chatbot/data/53-71 CJ5 Service Manual.pdf"
print("gen works")
"""

pathlib.Path("C:/Users/Troy Davis/dev/personal/manual-chatbot/output/validate_cj.py").write_text(SCRIPT.strip(), encoding="utf-8")
print(f"Written {len(SCRIPT)} chars")
