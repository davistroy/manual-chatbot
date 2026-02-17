import sys, statistics, traceback
from collections import Counter

sys.path.insert(0, "C:/Users/Troy Davis/dev/personal/manual-chatbot/src")

from pipeline import extract_pages
from pipeline.profile import load_profile, validate_profile, compile_patterns
from pipeline.ocr_cleanup import clean_page, assess_quality
from pipeline.structural_parser import detect_boundaries, filter_boundaries, validate_boundaries, build_manifest
from pipeline.chunk_assembly import assemble_chunks, count_tokens
from pipeline.qa import run_validation_suite

SEP = "=" * 70
DASH = "-" * 70

print(SEP)
print("TM 9-8014 PIPELINE VALIDATION REPORT")
print(SEP)

print()
print(DASH)
print("STAGE 0: PROFILE LOADING")
print(DASH)

profile = load_profile("C:/Users/Troy Davis/dev/personal/manual-chatbot/tests/fixtures/tm9_8014_profile.yaml")
validation_errors = validate_profile(profile)
print(f"Profile: {profile.manual_id} - {profile.manual_title}")
print(f"Schema version: {profile.schema_version}")
print(f"Vehicles: {[v.model for v in profile.vehicles]}")
print(f"Hierarchy levels: {len(profile.hierarchy)}")
for h in profile.hierarchy:
    print(f"  L{h.level} {h.name}: id={h.id_pattern!r} title={h.title_pattern!r}")
    if h.known_ids:
        print(f"    known_ids: {[k[chr(105)+chr(100)] for k in h.known_ids]}")
print(f"Validation errors: {validation_errors}")
compiled = compile_patterns(profile)
print(f"Compiled groups: {list(compiled.keys())}")

print()
print(DASH)
print("STAGE 1: PDF PAGE EXTRACTION")
print(DASH)

pages = extract_pages("C:/Users/Troy Davis/dev/personal/manual-chatbot/data/TM9-8014.pdf")
print(f"Total pages: {len(pages)}")
empty_pages = [i for i, p in enumerate(pages) if not p.strip()]
print(f"Empty pages: {len(empty_pages)} indices: {empty_pages[:20]}")
char_counts = [len(p) for p in pages]
if char_counts:
    print(f"Chars/page: min={min(char_counts)} max={max(char_counts)} mean={statistics.mean(char_counts):.0f}")
for i in range(min(5, len(pages))):
    print()
    print(f"--- Page {i} (first 300 chars) ---")
    print(pages[i][:300])

print()
print(DASH)
print("STAGE 2: OCR CLEANUP")
print(DASH)

cleaned = [clean_page(page, i, profile) for i, page in enumerate(pages)]
quality = assess_quality(cleaned)
print("OCR Quality:")
print(f"  Total pages: {quality.total_pages}")
print(f"  Sampled pages: {quality.sampled_pages}")
print(f"  Dictionary match rate: {quality.dictionary_match_rate:.3f}")
print(f"  Garbage line rate: {quality.garbage_line_rate:.3f}")
print(f"  Suspected errors: {quality.suspected_errors}")
print(f"  Needs re-OCR: {quality.needs_reocr}")

total_subs = sum(c.substitutions_applied for c in cleaned)
pages_with_subs = sum(1 for c in cleaned if c.substitutions_applied > 0)
print(f"  Substitutions: {total_subs} across {pages_with_subs} pages")

garbage_counts = [(i, len(c.garbage_lines)) for i, c in enumerate(cleaned)]
total_garbage = sum(g[1] for g in garbage_counts)
pages_with_garbage = sum(1 for g in garbage_counts if g[1] > 0)
garbage_counts.sort(key=lambda x: x[1], reverse=True)
print(f"  Total garbage lines: {total_garbage} across {pages_with_garbage} pages")
print(f"  Top 10 garbage pages: {garbage_counts[:10]}")

for i, c in enumerate(cleaned):
    if c.garbage_lines:
        cl = c.cleaned_text.split(chr(10))
        print(f"  Sample garbage from page {i}:")
        for gl in c.garbage_lines[:5]:
            if gl < len(cl):
                print(f"    Line {gl}: {cl[gl][:100]!r}")
        break

print()
print(DASH)
print("STAGE 3: STRUCTURAL PARSING")
print(DASH)

clean_texts = [c.cleaned_text for c in cleaned]
boundaries = detect_boundaries(clean_texts, profile)
print(f"Raw boundaries: {len(boundaries)}")
for level in range(1, 6):
    count = sum(1 for b in boundaries if b.level == level)
    if count > 0:
        lname = profile.hierarchy[level-1].name if level <= len(profile.hierarchy) else "?"
        print(f"  Level {level} ({lname}): {count}")

print()
print("All raw boundaries:")
for b in boundaries:
    print(f"  L{b.level} id=[{b.id}] title=[{b.title}] pg={b.page_number} ln={b.line_number}")

filtered = filter_boundaries(boundaries, profile, clean_texts)
print(f"Filtered boundaries: {len(filtered)}")
for level in range(1, 6):
    count = sum(1 for b in filtered if b.level == level)
    if count > 0:
        print(f"  Level {level}: {count}")

print()
print("All filtered boundaries:")
for b in filtered:
    print(f"  L{b.level} id=[{b.id}] title=[{b.title}] pg={b.page_number} ln={b.line_number}")

raw_set = {(b.level, b.line_number) for b in boundaries}
filt_set = {(b.level, b.line_number) for b in filtered}
removed = raw_set - filt_set
if removed:
    removed_b = [b for b in boundaries if (b.level, b.line_number) in removed]
    print(f"Removed by filtering: {len(removed_b)}")
    for b in removed_b[:30]:
        print(f"  L{b.level} id=[{b.id}] title=[{b.title}] pg={b.page_number} ln={b.line_number}")

warnings = validate_boundaries(filtered, profile)
print(f"Boundary validation warnings: {len(warnings)}")
for w in warnings[:30]:
    print(f"  {w}")

manifest = build_manifest(filtered, profile)
print(f"Manifest entries: {len(manifest.entries)}")
for entry in manifest.entries[:40]:
    print(f"  {entry.chunk_id} -- {entry.title} (L{entry.level}, lines {entry.line_range.start}-{entry.line_range.end})")

print()
print(DASH)
print("STAGE 4: CHUNK ASSEMBLY")
print(DASH)

chunks = None
tokens = None
report = None

try:
    chunks = assemble_chunks(clean_texts, manifest, profile)
    print(f"Total chunks: {len(chunks)}")

    tokens = [count_tokens(c.text) for c in chunks]
    if tokens:
        print(f"Token stats: min={min(tokens)} max={max(tokens)} mean={statistics.mean(tokens):.0f} median={statistics.median(tokens):.0f}")
        undersized = sum(1 for t in tokens if t < 200)
        oversized = sum(1 for t in tokens if t > 2000)
        in_range = len(tokens) - undersized - oversized
        print(f"  In range (200-2000): {in_range} ({in_range/len(chunks)*100:.1f}%)")
        print(f"  Undersized (<200): {undersized} ({undersized/len(chunks)*100:.1f}%)")
        print(f"  Oversized (>2000): {oversized} ({oversized/len(chunks)*100:.1f}%)")

        labels = ["0-100","101-200","201-400","401-600","601-800","801-1000","1001-1500","1501-2000","2001-3000","3001+"]
        thresholds = [100, 200, 400, 600, 800, 1000, 1500, 2000, 3000, float("inf")]
        buckets = [0]*10
        for t in tokens:
            for bi, threshold in enumerate(thresholds):
                if t <= threshold:
                    buckets[bi] += 1
                    break
        print()
        print("  Token distribution:")
        for label, count in zip(labels, buckets):
            bar = "#" * min(count, 50)
            print(f"    {label:>10}: {count:3d} {bar}")

    print()
    print("First 10 chunks:")
    for c in chunks[:10]:
        t = count_tokens(c.text)
        print(f"  {c.chunk_id} ({t} tok) first100: {c.text[:100]!r}")

    if tokens and oversized > 0:
        print()
        print("Oversized chunks (>2000 tokens):")
        for c in chunks:
            t = count_tokens(c.text)
            if t > 2000:
                print(f"  {c.chunk_id}: {t} tok first100: {c.text[:100]!r}")

    if tokens and undersized > 0:
        print()
        print("Undersized chunks (<200 tokens) first 20:")
        shown = 0
        for c in chunks:
            t = count_tokens(c.text)
            if t < 200:
                print(f"  {c.chunk_id}: {t} tok text: {c.text[:150]!r}")
                shown += 1
                if shown >= 20:
                    break

    print()
    print(DASH)
    print("STAGE 5: QA VALIDATION")
    print(DASH)

    report = run_validation_suite(chunks, profile)
    print(f"Checks run: {report.checks_run}")
    print(f"Total issues: {len(report.issues)}")
    print(f"  Errors: {report.error_count}")
    print(f"  Warnings: {report.warning_count}")
    print(f"  PASSED: {report.passed}")

    check_counts = Counter((i.check, i.severity) for i in report.issues)
    print()
    print("Issue breakdown:")
    for (check, sev), count in check_counts.most_common():
        print(f"  {check} ({sev}): {count}")

    print()
    print("Sample issues (first 30):")
    for issue in report.issues[:30]:
        print(f"  [{issue.severity}] {issue.check}: {issue.chunk_id} -- {issue.message}")
        if issue.details:
            print(f"    details: {issue.details}")

except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()

print()
print(SEP)
print("SUMMARY")
print(SEP)
print(f"Pages: {len(pages)}")
print(f"OCR quality: dict_match={quality.dictionary_match_rate:.3f} garbage={quality.garbage_line_rate:.3f} needs_reocr={quality.needs_reocr}")
print(f"Raw boundaries: {len(boundaries)}")
print(f"Filtered boundaries: {len(filtered)}")
print(f"Manifest entries: {len(manifest.entries)}")
if chunks is not None:
    print(f"Chunks: {len(chunks)}")
    if tokens:
        print(f"Token range: {min(tokens)}-{max(tokens)} mean={statistics.mean(tokens):.0f}")
    if report is not None:
        print(f"QA: {report.error_count} errors, {report.warning_count} warnings, passed={report.passed}")
print(SEP)
