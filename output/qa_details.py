import sys
sys.path.insert(0, "C:/Users/Troy Davis/dev/personal/manual-chatbot/src")
from pipeline.profile import load_profile
from pipeline import extract_pages
from pipeline.ocr_cleanup import clean_page
from pipeline.structural_parser import detect_boundaries, filter_boundaries, build_manifest
from pipeline.chunk_assembly import assemble_chunks
from pipeline.qa import run_validation_suite
from collections import Counter

profile = load_profile("C:/Users/Troy Davis/dev/personal/manual-chatbot/tests/fixtures/cj_universal_profile.yaml")
pages = extract_pages("C:/Users/Troy Davis/dev/personal/manual-chatbot/data/53-71 CJ5 Service Manual.pdf")
cleaned = [clean_page(page, i, profile) for i, page in enumerate(pages)]
ctexts = [c.cleaned_text for c in cleaned]
bounds = detect_boundaries(ctexts, profile)
filt = filter_boundaries(bounds, profile, ctexts)
manifest = build_manifest(filt, profile)
chunks = assemble_chunks(ctexts, manifest, profile)
rpt = run_validation_suite(chunks, profile)

print("=== ERROR-LEVEL ISSUES ===")
for i in rpt.issues:
    if i.severity == "error":
        print(f"  {i.check}: {i.message}")
print()
print("=== PROFILE_VALIDATION WARNINGS (first 20) ===")
pv = [i for i in rpt.issues if i.check == "profile_validation"]
for i in pv[:20]:
    print(f"  {i.message}")
print(f"Total profile_validation: {len(pv)}")
print()
print("=== UNIQUE L1 IDS IN BOUNDARIES ===")
l1ids = Counter(b.id for b in filt if b.level == 1)
for bid, cnt in l1ids.most_common():
    print(f"  {bid}: {cnt}")
