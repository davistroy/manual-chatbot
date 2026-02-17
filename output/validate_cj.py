import sys, traceback, statistics
from collections import Counter

sys.path.insert(0, "C:/Users/Troy Davis/dev/personal/manual-chatbot/src")
PROF = "C:/Users/Troy Davis/dev/personal/manual-chatbot/tests/fixtures/cj_universal_profile.yaml"
PDF = "C:/Users/Troy Davis/dev/personal/manual-chatbot/data/53-71 CJ5 Service Manual.pdf"

def main():
    SEP = "=" * 70
    NL = chr(10)
    PIPE = chr(32) + chr(124) + chr(32)

    print(SEP); print("STAGE 0: PROFILE"); print(SEP)
    from pipeline.profile import load_profile, validate_profile, compile_patterns
    profile = load_profile(PROF)
    errs = validate_profile(profile)
    print(f"Profile: {profile.manual_id}")
    print(f"Title: {profile.manual_title}")
    print(f"Vehicles: {[v.model for v in profile.vehicles]}")
    for h in profile.hierarchy:
        print(f"  L{h.level} ({h.name}): pattern={h.id_pattern!r}, known_ids={len(h.known_ids)}")
    print(f"Step patterns: {profile.step_patterns}")
    print(f"Safety callouts: {len(profile.safety_callouts)}")
    print(f"OCR: q={profile.ocr_cleanup.quality_estimate}, subs={len(profile.ocr_cleanup.known_substitutions)}, hdrs={len(profile.ocr_cleanup.header_footer_patterns)}")
    print(f"Validation errors: {errs}")
    compiled = compile_patterns(profile)
    print(f"Compiled: {list(compiled.keys())}")
    print()

    print(SEP); print("STAGE 1: PDF EXTRACTION"); print(SEP)
    from pipeline import extract_pages
    pages = extract_pages(PDF)
    print(f"Pages: {len(pages)}")
    empty = sum(1 for p in pages if not p.strip())
    print(f"Empty pages: {empty}")
    for i in range(min(3, len(pages))):
        print(f"  Page {i}: {pages[i][:200].replace(NL, PIPE)}...")
    tc = sum(len(p) for p in pages)
    print(f"Total chars: {tc:,}")
    pl = [len(p) for p in pages]
    print(f"Page len: min={min(pl)}, max={max(pl)}, mean={statistics.mean(pl):.0f}")
    print()

    print(SEP); print("STAGE 2: OCR CLEANUP"); print(SEP)
    from pipeline.ocr_cleanup import clean_page, assess_quality
    cleaned = [clean_page(page, i, profile) for i, page in enumerate(pages)]
    q = assess_quality(cleaned)
    print(f"Dict match rate: {q.dictionary_match_rate:.3f}")
    print(f"Garbage line rate: {q.garbage_line_rate:.3f}")
    print(f"Suspected errors: {q.suspected_errors}")
    print(f"Needs re-OCR: {q.needs_reocr}")
    ts = sum(c.substitutions_applied for c in cleaned)
    ps = sum(1 for c in cleaned if c.substitutions_applied > 0)
    print(f"Substitutions: {ts} across {ps} pages")
    tg = sum(len(c.garbage_lines) for c in cleaned)
    pg = sum(1 for c in cleaned if c.garbage_lines)
    print(f"Garbage lines: {tg} across {pg} pages")
    pids = [c.extracted_page_id for c in cleaned if c.extracted_page_id]
    print(f"Page IDs: {len(pids)}/{len(cleaned)}")
    if pids[:10]:
        print(f"  Sample: {pids[:10]}")
    for i in [0, 5, 50]:
        if i < len(cleaned):
            print(f"  Cleaned[{i}]: {cleaned[i].cleaned_text[:200].replace(NL, PIPE)}...")
    print()

    print(SEP); print("STAGE 3: STRUCTURAL PARSING"); print(SEP)
    from pipeline.structural_parser import detect_boundaries, filter_boundaries, validate_boundaries, build_manifest
    ctexts = [c.cleaned_text for c in cleaned]
    bounds = detect_boundaries(ctexts, profile)
    print(f"Raw boundaries: {len(bounds)}")
    for lv in range(1, 5):
        ct = sum(1 for b in bounds if b.level == lv)
        if ct: print(f"  Level {lv}: {ct}")
    l1r = [b for b in bounds if b.level == 1]
    print(f"Raw L1 ({len(l1r)}):")
    for b in l1r[:50]:
        print(f"  [{b.id}] {b.title} (pg {b.page_number}, ln {b.line_number})")
    l2r = [b for b in bounds if b.level == 2]
    print(f"Raw L2 (first 30 of {len(l2r)}):")
    for b in l2r[:30]:
        print(f"  [{b.id}] {b.title} (pg {b.page_number}, ln {b.line_number})")
    filt = filter_boundaries(bounds, profile, ctexts)
    print(f"Filtered: {len(filt)}")
    for lv in range(1, 5):
        ct = sum(1 for b in filt if b.level == lv)
        if ct: print(f"  Level {lv}: {ct}")
    l1f = [b for b in filt if b.level == 1]
    print(f"Filtered L1 ({len(l1f)}):")
    for b in l1f:
        print(f"  [{b.id}] {b.title} (pg {b.page_number}, ln {b.line_number})")
    l2f = [b for b in filt if b.level == 2]
    print(f"Filtered L2 (first 40 of {len(l2f)}):")
    for b in l2f[:40]:
        print(f"  [{b.id}] {b.title} (pg {b.page_number}, ln {b.line_number})")
    warns = validate_boundaries(filt, profile)
    print(f"Boundary warnings: {len(warns)}")
    for w in warns[:40]:
        print(f"  {w}")
    if len(warns) > 40:
        print(f"  ... and {len(warns)-40} more")
    manifest = build_manifest(filt, profile)
    print(f"Manifest entries: {len(manifest.entries)}")
    print(f"Manual ID: {manifest.manual_id}")
    print("First 20 entries:")
    for e in manifest.entries[:20]:
        print(f"  {e.chunk_id} | L{e.level} | {e.title[:50]} | pg {e.page_range.start}-{e.page_range.end} | ln {e.line_range.start}-{e.line_range.end}")
    print()

    print(SEP); print("STAGE 4: CHUNK ASSEMBLY"); print(SEP)
    from pipeline.chunk_assembly import assemble_chunks, count_tokens
    chunks = assemble_chunks(ctexts, manifest, profile)
    print(f"Total chunks: {len(chunks)}")
    if not chunks:
        print("NO CHUNKS")
        return
    toks = [count_tokens(c.text) for c in chunks]
    print(f"Token stats: min={min(toks)}, max={max(toks)}, mean={statistics.mean(toks):.0f}, median={statistics.median(toks):.0f}")
    if len(toks) > 1:
        print(f"  stdev={statistics.stdev(toks):.0f}")
    us = sum(1 for t in toks if t < 200)
    ov = sum(1 for t in toks if t > 2000)
    ir = sum(1 for t in toks if 200 <= t <= 2000)
    n = len(chunks)
    print(f"Undersized(<200): {us} ({us/n*100:.1f}%)")
    print(f"In range(200-2000): {ir} ({ir/n*100:.1f}%)")
    print(f"Oversized(>2000): {ov} ({ov/n*100:.1f}%)")
    bkts = [0]*10
    for t in toks:
        bkts[min(t//200, 9)] += 1
    print("Token histogram:")
    labs = ["0-199","200-399","400-599","600-799","800-999","1000-1199","1200-1399","1400-1599","1600-1799","1800+"]
    for lb, ct in zip(labs, bkts):
        print(f"  {lb:>10}: {ct:4d} " + "#"*min(ct,60))
    print("First 10 chunks:")
    for c in chunks[:10]:
        t = count_tokens(c.text)
        print(f"  {c.chunk_id} ({t} tok): {c.text[:120].replace(NL, PIPE)}...")
    sbs = sorted(zip(toks, chunks), key=lambda x: x[0])
    print("5 smallest:")
    for t, c in sbs[:5]:
        print(f"  {c.chunk_id} ({t} tok): {c.text[:100].replace(NL, PIPE)}...")
    print("5 largest:")
    for t, c in sbs[-5:]:
        print(f"  {c.chunk_id} ({t} tok): {c.text[:100].replace(NL, PIPE)}...")
    print("Metadata keys:")
    mk = Counter()
    for c in chunks:
        for k in c.metadata: mk[k] += 1
    for k, v in mk.most_common():
        print(f"  {k}: {v}/{n} ({v/n*100:.0f}%)")
    vt = sum(1 for c in chunks if c.metadata.get("vehicle_applicability"))
    et = sum(1 for c in chunks if c.metadata.get("engine_applicability"))
    print(f"Vehicle tagged: {vt}/{n}, Engine tagged: {et}/{n}")
    print()

    print(SEP); print("STAGE 5: QA VALIDATION"); print(SEP)
    from pipeline.qa import run_validation_suite
    rpt = run_validation_suite(chunks, profile)
    print(f"Checks: {rpt.checks_run}")
    print(f"Issues: {len(rpt.issues)} (errors={rpt.error_count}, warnings={rpt.warning_count})")
    print(f"PASSED: {rpt.passed}")
    cc = Counter((i.check, i.severity) for i in rpt.issues)
    print("Issue breakdown:")
    for (ck, sv), ct in cc.most_common():
        print(f"  {ck} ({sv}): {ct}")
    print("Sample issues (first 40):")
    for issue in rpt.issues[:40]:
        print(f"  [{issue.severity}] {issue.check}: {issue.message}")
    if len(rpt.issues) > 40:
        print(f"  ... and {len(rpt.issues)-40} more")
    print()
    print(SEP); print("SUMMARY"); print(SEP)
    print(f"Pages: {len(pages)}")
    print(f"OCR re-OCR needed: {q.needs_reocr}")
    print(f"Boundaries raw/filtered: {len(bounds)}/{len(filt)}")
    print(f"Warnings: {len(warns)}")
    print(f"Manifest entries: {len(manifest.entries)}")
    print(f"Chunks: {n}")
    print(f"In-range: {ir}/{n} ({ir/n*100:.1f}%)")
    print(f"QA: passed={rpt.passed}, errors={rpt.error_count}, warnings={rpt.warning_count}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        traceback.print_exc()
