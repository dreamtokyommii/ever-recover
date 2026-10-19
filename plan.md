# Recovery Tool — Development Plan

## 0. Ground Rules for This Plan

- Every section below must produce **working functionality**, not a UI shell. "Done" means: real data goes in, a real algorithm runs on it, real results come back and render in the dashboard.
- Before writing new code, the codebase must be audited first (see Section 8 — Codebase Audit) so we know what already works, what's a stub, and what's dead weight. Nothing gets built twice, and nothing fake gets left behind pretending to be real.
- The tool recovers **deleted files** — this means reading raw disk/partition data (or a disk image), not just querying the OS file explorer. That's the part that has to be real.

---

## 1. Architecture Overview

Three layers, cleanly separated so the dashboard is never running recovery logic itself:

```
┌─────────────────────────────────────────────┐
│  Dashboard (UI) — sectioned, click-nav        │
│  Home | Settings | Scan | Timeline | Review   │
│  | Report                                     │
└───────────────┬────────────────────────────┘
                │  app state / IPC / API calls
┌───────────────▼────────────────────────────┐
│  Engine Core (orchestration)                  │
│  - Job manager (scan jobs, progress, cancel)  │
│  - Filesystem detector                        │
│  - Result store (in-memory + persisted)       │
└───────┬─────────────────┬────────────────────┘
        │                 │
┌───────▼───────┐ ┌───────▼────────────────┐
│ FS Parsers     │ │ Carving Engine          │
│ NTFS / FAT32-  │ │ Signature-based deep    │
│ exFAT / ext2-3-│ │ scan, fragment recovery │
│ 4 / APFS / HFS+│ │                         │
└────────────────┘ └─────────────────────────┘
        │                 │
        └────────┬────────┘
                 ▼
        Raw device / image reader
     (sector-level access, read-only)
```

**Non-negotiable design rule:** the UI never talks to disks directly. It only talks to the Engine Core through one interface (job start/stop/progress/results). This is what lets every dashboard section be "fully functional" instead of faking data — they're all just different views onto the same real job/result objects.

---

## 2. Dashboard — Sectioned, Click-Nav Layout

Sections (left nav or top tabs, click to switch, state persists across switches — not remounted from scratch):

1. **Home / Overview** — connected sources, recent jobs, quick-start button
2. **Settings** — see Section 3
3. **Scan** — live scan in progress: filesystem detected, % complete, entries found so far, cancel button
4. **Timeline** — see Section 5
5. **Review** — see Section 6
6. **Report** — see Section 7

Each section reads from a shared `ScanJob` / `ScanResult` object (source, filesystem, profile, found entries, timestamps, status). No section invents its own mock data — if Scan hasn't run yet, Review and Report show an honest empty state with a "run a scan first" prompt, not fake rows.

---

## 3. Settings Interface

| Field | What it actually does |
|---|---|
| **Source** | Picks the raw target: physical drive, partition/volume, or a disk image file (.img/.dd/.e01). Must resolve to a byte-offset-readable handle, not just a folder path. |
| **Output folder** | Where recovered files get written on successful recovery. Validated for write access and free space before scan starts. |
| **File system** | Manual override OR "Auto Detect" (see Section 4). Locks which parser module the engine loads. |
| **Scan mode** | Quick Scan or Deep Carve — see Section 4.2. Determines whether the engine reads filesystem metadata structures or raw-carves the whole device. |

Settings validate before "Start Scan" is enabled: source must be readable, output folder must be writable and not be the same device/partition as source (to avoid overwriting evidence).

---

## 4. Scan Types & Profiles

### 4.1 Filesystem Detection (Auto Detect + manual options)

Auto-detect reads the boot sector / superblock / volume header at known offsets and checks magic signatures:

- **NTFS** — boot sector, "NTFS " OEM ID at offset 0x03
- **FAT32/exFAT** — boot sector signature 0x55AA, `FAT32`/`EXFAT` label check
- **ext4** — superblock at offset 1024, magic `0xEF53`, feature flags distinguish ext4 from ext2/3
- **ext3/ext2** — same superblock magic, distinguished from ext4 by absence of extents/journal feature flags
- **APFS** — container superblock (`NXSB` magic) at offset 0
- **HFS+** — volume header, `H+` / `HX` signature at offset 1024

If auto-detect is ambiguous or the header is damaged (common with deleted/corrupted partitions), fall back to manual selection — user picks from the same six options.

### 4.2 Scan Profiles

- **Quick Scan** — parses the filesystem's own bookkeeping structures to find entries marked deleted but not yet overwritten:
  - NTFS: walk the `$MFT`, find records flagged unallocated, recover filename/size/timestamps from resident attributes
  - FAT32/exFAT: scan directory entries with the deleted marker (`0xE5`), reconstruct from the FAT chain if not yet reused
  - ext2/3/4: scan inode table entries with deleted flag / zeroed link count, cross-reference directory entries; ext3/4 journal replay recovers very recent deletions
  - APFS: scan the checkpoint/space-manager metadata for snapshot or unlinked-but-unreclaimed objects
  - HFS+: scan catalog B-tree for entries not yet reclaimed
  - Fast (minutes), high accuracy on files, low overwrite recovery
- **Deep Carve** — ignores filesystem metadata entirely, reads every sector and matches against a **file signature database** (magic numbers + footer patterns) for JPEG, PNG, PDF, DOCX/ZIP-based formats, MP4, ZIP, RAR, SQLite, etc. Reconstructs fragmented files using contiguity heuristics + format-aware validation (e.g. can this be a valid JPEG stream, does the ZIP central directory parse). Slow (can be hours), works even when the filesystem itself is destroyed, no filenames/timestamps unless embedded in the recovered file itself.

### 4.3 Timeline Scanning

A dedicated pass (usable after Quick Scan or standalone) that builds a chronological event view from every timestamp field the filesystem exposes:

- NTFS: `$STANDARD_INFORMATION` and `$FILE_NAME` created/modified/MFT-changed/accessed timestamps (including the divergence between the two attributes, which is a classic forensic tamper signal)
- ext-family: inode ctime/mtime/atime, and `dtime` (deletion time) where present
- FAT: creation/modified/accessed date fields (coarse resolution)
- APFS/HFS+: catalog record timestamps

Output: a sortable, filterable (by date range, file type, event type — created/modified/deleted) timeline view, feeding the Timeline dashboard section directly. This is real parsing output, not a decorative UI.

---

## 5. Timeline Section (Dashboard)

- Horizontal/vertical timeline, zoomable by day/week/month
- Filter by: event type (created/modified/deleted/accessed), file type, filename pattern
- Click an event → jumps to that file in Review with full metadata
- Backed entirely by the timestamp data produced in 4.3, not sample data

---

## 6. File / Review Section

- Table + preview pane of every recovered/found entry: name (if known), size, original path (if recoverable), filesystem timestamps, recovery confidence (e.g. "metadata intact" vs "carved, unverified")
- Preview pane renders actual content where possible: image thumbnail, text snippet, hex view fallback for anything else
- Search, filter (by type/size/date/confidence), sort
- Multi-select → "Recover selected" writes real bytes to the Output folder from Settings, with progress and per-file success/failure status
- Recovered file integrity check post-write (size match, and format validation for carved files) so failures are reported honestly rather than silently marked "recovered"

---

## 7. Report Section

- Auto-generated after any scan/recovery run, not a static template
- Contents: source device/image identifiers, scan profile used, filesystem detected, start/end time, total entries found, total recovered, failure list with reasons, hash (SHA-256) of each recovered file for chain-of-custody use
- Export formats: PDF and CSV/JSON at minimum
- Report is regenerated from the actual `ScanResult`/recovery log objects — never hand-typed or mocked

---

## 8. Codebase Audit (must happen before new work starts)

1. Inventory every existing dashboard section — mark each **real** (wired to actual engine output) or **placeholder** (static/mock).
2. Inventory the engine/backend — is there already a raw device reader? Any filesystem parsing at all? Any carving/signature matching? What language/framework is it in?
3. Identify what's reusable vs. what needs replacing (e.g. a placeholder "Report" that just renders hardcoded JSON gets thrown out, not extended).
4. Confirm platform target (Windows/macOS/Linux) since raw device access APIs differ significantly (`\\.\PhysicalDriveN` on Windows vs `/dev/sdX` on Linux vs `/dev/diskN` on macOS, plus permission models for each).

---

## 9. Build Order (phased, each phase ships something real end-to-end)

| Phase | Deliverable |
|---|---|
| 1 | Raw source reader (drive/partition/image) + filesystem auto-detect, wired to Settings + Scan sections |
| 2 | One filesystem parser end-to-end (recommend NTFS or FAT32 first — most common) for Quick Scan, results flowing into Review |
| 3 | Remaining filesystem parsers (exFAT, ext2/3/4, APFS, HFS+) |
| 4 | Deep Carve engine (signature DB + carving + fragment reconstruction) |
| 5 | Timeline extraction + Timeline dashboard section |
| 6 | Recovery-to-disk (Output folder) with integrity verification |
| 7 | Report generation (PDF/CSV/JSON) from real scan/recovery logs |
| 8 | Full dashboard integration pass — every section sharing one live `ScanJob` state, no orphaned mock data anywhere |
| 9 | Test pass against known-good test images per filesystem (see Section 10) |

---

## 10. Testing Strategy

- Build/obtain small test disk images per filesystem type with known deleted files (known content, known hashes) — this is the only reliable way to verify "recovery" actually recovers the right bytes, not just something.
- Automated test: run Quick Scan + Deep Carve against each image, assert recovered file hashes match expected originals.
- Corruption/edge cases: partially overwritten files, fragmented files, damaged boot sector/superblock (forces the auto-detect fallback path).

---

## 11. Open Questions to Resolve Early

- Target platform(s) — affects raw device access strategy significantly
- Framework/stack for the dashboard (web-based/Electron vs native) — affects how sections share state
- Whether disk images (.img/.dd/.e01) must be supported in addition to live devices
- Elevated-privilege requirement: raw disk access needs admin/root — how is that handled in the UI (prompt, service, etc.)