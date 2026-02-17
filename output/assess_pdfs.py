"""PDF Assessment Script - Characterize unprocessed PDFs for pipeline candidacy."""
from __future__ import annotations

import re
import sys
from collections import Counter

sys.path.insert(0, "C:/Users/Troy Davis/dev/personal/manual-chatbot/src")
from pipeline import extract_pages

pdfs = [
    ("TM9-8015-1", "C:/Users/Troy Davis/dev/personal/manual-chatbot/data/TM9-8015-1.pdf"),
    ("TM9-8015-2", "C:/Users/Troy Davis/dev/personal/manual-chatbot/data/TM9-8015-2.pdf"),
    ("M38A1wiring", "C:/Users/Troy Davis/dev/personal/manual-chatbot/data/M38A1wiring.pdf"),
    ("ORD_SNL_G-758", "C:/Users/Troy Davis/dev/personal/manual-chatbot/data/ORD_SNL_G-758.pdf"),
]

for name, path in pdfs:
    print(f"\n{'='*70}")
    print(f"ANALYZING: {name}")
    print(f"  Path: {path}")
    print(f"{'='*70}")

    try:
        pages = extract_pages(path)
        print(f"Total pages: {len(pages)}")
        empty = sum(1 for p in pages if not p.strip())
        print(f"Empty pages: {empty}")

        total_chars = sum(len(p) for p in pages)
        printable_chars = sum(
            sum(1 for c in p if c.isprintable() or c in '\n\r\t') for p in pages
        )
        if total_chars > 0:
            print(f"Total characters: {total_chars:,}")
            print(f"Printable ratio: {printable_chars/total_chars:.4f} ({printable_chars/total_chars*100:.1f}%)")

        non_empty_pages = [p for p in pages if p.strip()]
        avg_chars = total_chars / max(len(pages), 1)
        avg_chars_nonempty = total_chars / max(len(non_empty_pages), 1) if non_empty_pages else 0
        print(f"Avg chars/page (all): {avg_chars:.0f}")
        print(f"Avg chars/page (non-empty): {avg_chars_nonempty:.0f}")
        if avg_chars < 50:
            print("  ** WARNING: Very low text content - likely scanned images without OCR")
        elif avg_chars < 200:
            print("  ** WARNING: Low text content - may be partially scanned or diagram-heavy")

        print(f"\n--- SAMPLE PAGES (first 500 chars, newlines shown as \n) ---")
        shown = 0
        for i, text in enumerate(pages):
            if not text.strip():
                continue
            display = text[:500].replace('\n', '\n')
            print(f"\n  Page {i}: {display}")
            shown += 1
            if shown >= 5:
                break

        if len(non_empty_pages) > 10:
            mid = len(pages) // 2
            for offset in range(20):
                for try_idx in [mid + offset, mid - offset]:
                    if 0 <= try_idx < len(pages) and pages[try_idx].strip():
                        text = pages[try_idx][:500].replace('\n', '\n')
                        print(f"\n  Page {try_idx} (near middle): {text}")
                        break
                else:
                    continue
                break

        for i in range(len(pages) - 1, -1, -1):
            if pages[i].strip():
                text = pages[i][:500].replace('\n', '\n')
                print(f"\n  Page {i} (last non-empty): {text}")
                break

        print(f"\n--- STRUCTURAL MARKER ANALYSIS ---")
        chapter_count = sum(1 for p in pages for line in p.split('\n')
                           if re.match(r'^\s*CHAPTER\s+\d+', line, re.I))
        section_count = sum(1 for p in pages for line in p.split('\n')
                           if re.match(r'^\s*Section\s+[IVXLC]+', line, re.I))
        paragraph_count = sum(1 for p in pages for line in p.split('\n')
                              if re.match(r'^\s*\d+-\d+\.', line))
        tm_header_count = sum(1 for p in pages for line in p.split('\n')
                              if re.match(r'^\s*TM\s+9-\d+', line))
        fig_count = sum(1 for p in pages for line in p.split('\n')
                        if re.search(r'[Ff]ig\.?\s*\d+', line))
        table_count = sum(1 for p in pages for line in p.split('\n')
                          if re.match(r'^\s*Table\s+\d+', line, re.I))
        warning_count = sum(1 for p in pages for line in p.split('\n')
                            if re.match(r'^\s*(WARNING|CAUTION|NOTE)\b', line))
        part_number_count = sum(1 for p in pages for line in p.split('\n')
                                if re.search(r'\b\d{7}\b', line))
        toc_markers = sum(1 for p in pages for line in p.split('\n')
                          if re.search(r'TABLE\s+OF\s+CONTENTS|CONTENTS', line, re.I))

        print(f"  CHAPTER headers: {chapter_count}")
        print(f"  Section headers: {section_count}")
        print(f"  Paragraph markers (e.g., 3-1.): {paragraph_count}")
        print(f"  TM headers: {tm_header_count}")
        print(f"  Figure references: {fig_count}")
        print(f"  Table references: {table_count}")
        print(f"  WARNING/CAUTION/NOTE: {warning_count}")
        print(f"  7-digit part/NSN numbers: {part_number_count}")
        print(f"  TOC markers: {toc_markers}")

        alpha_chars = sum(1 for p in pages for c in p if c.isalpha())
        digit_chars = sum(1 for p in pages for c in p if c.isdigit())
        space_chars = sum(1 for p in pages for c in p if c.isspace())
        other_chars = total_chars - alpha_chars - digit_chars - space_chars
        print(f"\n--- CHARACTER DISTRIBUTION ---")
        print(f"  Alpha: {alpha_chars:,} ({alpha_chars/max(total_chars,1)*100:.1f}%)")
        print(f"  Digit: {digit_chars:,} ({digit_chars/max(total_chars,1)*100:.1f}%)")
        print(f"  Space: {space_chars:,} ({space_chars/max(total_chars,1)*100:.1f}%)")
        print(f"  Other: {other_chars:,} ({other_chars/max(total_chars,1)*100:.1f}%)")

        all_words = []
        for p in pages:
            all_words.extend(w.lower() for w in p.split() if len(w) > 3 and w.isalpha())
        word_freq = Counter(all_words)
        print(f"\n--- TOP 30 WORDS (len>3, alpha only) ---")
        for word, count in word_freq.most_common(30):
            print(f"  {word:20s} {count:5d}")

        print(f"\n--- DOCUMENT TYPE INDICATORS ---")
        full_text = "\n".join(pages).lower()
        indicators = {
            "Parts list/catalog": any(kw in full_text for kw in ["parts list", "stock number", "national stock", "nsn", "nomenclature"]),
            "Wiring diagram": any(kw in full_text for kw in ["wiring diagram", "wiring harness", "circuit", "schematic"]),
            "Service/repair manual": any(kw in full_text for kw in ["maintenance", "repair", "troubleshooting", "inspection", "disassembly"]),
            "Operator manual": any(kw in full_text for kw in ["operator", "operation", "controls and instruments"]),
            "Lubrication order": any(kw in full_text for kw in ["lubrication order", "lubricant", "lube point"]),
            "Organizational maint.": any(kw in full_text for kw in ["organizational maintenance"]),
            "Direct/General support": any(kw in full_text for kw in ["direct support", "general support"]),
        }
        for label, found in indicators.items():
            print(f"  {label:30s} {'YES' if found else 'no'}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*70}")
print("ASSESSMENT COMPLETE")
print(f"{'='*70}")
