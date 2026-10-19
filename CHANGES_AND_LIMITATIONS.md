# Ever Recover — Fixes Applied & Known Limitations

This document covers everything changed in this pass: diagnosis, exact
files/functions modified, what was verified and how, and an honest list of
what still cannot be solved by the current architecture.

## How to verify this yourself

```bash
pip install -r requirements.txt pytest
python -m pytest tests/ -v          # 31 tests, all pass as of this delivery
python ever_recover.py              # launch the GUI (Windows)
```

The regression tests specific to this pass live in `tests/regression/`:
- `test_carving_boundary_fix.py` — proves the chunk-truncation bug is fixed
  with byte-exact recovery of files 3-4x the old 1MB cap, headers
  straddling chunk boundaries, and OOXML subtype disambiguation.
- `test_ext4_parser.py` — builds and mounts a **real** `mkfs.ext4` image
  (not synthetic bytes), writes/deletes real files, and verifies recovery
  and honest deletion reporting against real on-disk behavior (skipped
  automatically if `mkfs.ext4`/root aren't available).

## 1. Administrator / elevation

**Problem:** `core/services/privilege_manager.py::request_elevation()`
(correct UAC `ShellExecuteW('runas', ...)` call) existed but was never
invoked. Failures dead-ended in a plain error dialog.

**Fix:** `dashboard_main.py` now has a dedicated `scan_requires_elevation`
/ `requires_elevation` signal path. `PermissionError`/`AccessDeniedError`
raised during a scan are caught specifically (not lumped into the generic
failure handler) and routed to `MainWindow._on_requires_elevation()`,
which offers a real "Restart as Administrator" prompt, calls
`request_elevation()`, and exits the current process on success so only
one process holds the device. If already elevated and access still fails,
the user is told it's a genuine access problem (locked/in-use device), not
a privilege gap — no infinite re-elevation loop.

**Verified:** logic path traced and unit-testable pieces confirmed; the
actual UAC prompt and process relaunch cannot be exercised outside a real
Windows session (this development environment is Linux-only) — see
Limitations.

## 2. Physical drive access was structurally broken

**Problem:** `infrastructure/disk/windows_disk_reader.py::_normalize_device_path()`
checked for `\\.\\ ` (two backslashes after the dot) as the "already
normalized" prefix, but real Windows device paths (`\\.\PhysicalDrive0`)
only have one. The check never matched, so correctly-formatted physical
drive paths fell through every branch and raised `InvalidDeviceError` —
independent of admin rights.

**Fix:** corrected to `\\.\` / `\\?\` (single backslash after dot).

**Verified:** direct string test confirming the corrected check matches
real device path formats (`\\.\PhysicalDrive0`, `\\.\PhysicalDrive15`,
`\\.\C:`, `\\?\Volume{guid}`) and rejects non-device paths.

## 3. Carving engine truncated every file above ~1MB — the actual video-recovery bug

**Problem:** `core/services/carving_engine.py` read the disk in
independent, non-overlapping 1MB chunks. Once a header was found, both
size calculation and footer search were bounded to `len(chunk) -
header_offset` — the current chunk only. Any file larger than the
remaining chunk bytes (almost every video, most documents/archives above
1MB) was silently truncated and still reported as "recovered." Headers
straddling a chunk boundary were missed entirely (no overlap).

**Fix:** full rewrite.
- Chunks are read with an overlap equal to the longest signature header,
  so boundary-straddling headers are detected; duplicates from the
  overlap are filtered by absolute offset.
- Extent resolution (`_resolve_extent` and friends) reads directly from
  the disk reader at the file's real offset, streamed in bounded windows
  — never bounded by chunk size.
- Real structural size determination, using each format's own declared
  layout instead of blind footer search:
  - **RIFF** (AVI/WAV/WebP): reads the declared chunk size field directly.
  - **MP4/MOV**: walks top-level ISO-BMFF atoms/boxes (handles 32-bit,
    64-bit extended, and "extends to EOF" box sizes).
  - **MKV/WebM**: parses the EBML header + Segment element size (vint
    decoding); reports unverified/capped when the Segment uses the
    reserved "unknown size" marker (common in streamed/live-muxed files).
  - **FLV**: walks the tag stream (PreviousTagSize + 11-byte tag header +
    data) to find the real end.
  - **ZIP/DOCX/XLSX/PPTX**: locates the real End-Of-Central-Directory
    record (scanning for the *last* occurrence, since deflated file data
    could coincidentally contain the same 4 bytes) and includes the
    trailing comment-length field, not just a naive footer search.
  - **PDF**: added the `%%EOF` terminal marker (previously undefined —
    PDF fell back to a pure size cap with no real boundary detection at
    all).
- Every `CarvedFile` now carries `size_verified` and `carve_method`, and
  confidence is downgraded whenever size wasn't structurally confirmed —
  so the UI can never report high confidence for a capped/guessed size.

**Verified:** byte-exact recovery (SHA-256 match) of a JPEG, a ~3MB AVI,
and a ~4MB MP4 in a synthetic image, including a header deliberately
placed to straddle a 1MB chunk boundary. Full pre-existing test suite (26
tests) re-verified passing after this rewrite, catching and fixing two
regressions I introduced myself in the process (see "Self-correction"
below) plus two real signature-collision bugs (see #4).

## 4. Signature collisions silently mislabeled/dropped files

**Problem found during testing (not part of the original diagnosis):**
- AVI, WAV, and WebP all share the identical raw `RIFF` header signature
  in `core/models/file_signature.py`. The carving engine's structural
  resolver didn't check the actual RIFF form-type FourCC (`AVI `, `WAVE`,
  `WEBP`), so whichever signature was tried first in list order silently
  claimed every RIFF match and the other two were discarded as
  "duplicates" at that offset — even when they were the genuinely correct
  type.
- MKV and WebM share the identical EBML magic bytes (WebM is technically
  a constrained Matroska profile) with the same collision risk.
- DOCX/XLSX/PPTX/ZIP all share the identical `PK\x03\x04` ZIP signature.

**Fix:** RIFF resolution now verifies the form-type FourCC; EBML
resolution parses the actual `DocType` element (`matroska` vs `webm`);
ZIP-family resolution scans early archive entries for the OOXML
type-specific folder (`word/`, `xl/`, `ppt/`) to distinguish
docx/xlsx/pptx from a generic zip.

**Verified:** dedicated regression tests build real zip/xlsx/docx
structures (via Python's `zipfile`) and confirm correct disambiguation.

## 5. EXT4/EXT3/EXT2 support was fake

**Problem:** `infrastructure/filesystems/ext4_parser.py`,
`apfs_parser.py`, `hfs_parser.py` were three near-identical stub files.
`initialize()` returned `True` (claimed success); `enumerate_files()`/
`get_deleted_files()` were empty generators. Selecting EXT4 reported a
successful scan with zero files — a silent false success.

**Fix:** `ext4_parser.py` rewritten with real, from-scratch parsing:
- Superblock parsing (validates the `0xEF53` magic, block size, layout).
- Block group descriptor table + inode table lookup.
- Both data-mapping schemes: ext4 extent trees, and classic ext2/ext3
  direct + single/double/triple indirect block pointers.
- Recursive directory walking from the root inode to enumerate existing
  files.
- Heuristic deleted-inode scan (`dtime != 0`, `links_count == 0`).

**Verified against a real `mkfs.ext4` image** (not synthetic bytes):
built a genuine ext4 filesystem, wrote a text file and a 500KB binary
file, and recovered both byte-for-byte (SHA-256 match) via
`enumerate_files()` + `get_file_data()`.

**Self-correction found via testing:** my first pass filtered out
zero-size deleted inodes, assuming only block/extent pointers get cleared
on unlink. Testing against the real image (`debugfs -R "stat <inode>"`)
showed modern ext4 actually clears `Size` and `Blockcount` to 0 on
deletion too — a genuine filesystem-level behavior, not a parser gap.
Fixed: deleted inodes are now always reported (never silently dropped),
with `content_recoverable`/`size_recoverable` flags set accurately based
on what's actually still present, rather than hiding the fact that
something was deleted.

## 6. APFS/HFS+ now fail honestly instead of faking success

**Fix:** `apfs_parser.py`/`hfs_parser.py` now raise
`FileSystemParserError` from `initialize()` with a clear message, instead
of claiming success and returning zero files.

**Related bug found and fixed:** `dashboard_main.py::_create_parser()`
called `parser.initialize()`/`parse_metadata()` **outside** the existing
carving-fallback try/except, so any initialization failure — including
this new honest APFS/HFS+ error, or a genuinely corrupted NTFS/FAT32
volume — would have crashed the whole scan instead of degrading to
carving-only. Moved inside the fallback logic.

## 7. Device picker (external-device support)

**Problem:** the shipped UI (`dashboard_main.py`) had only a plain text
box + folder browser for the scan source — no way to see or select an
actual physical drive/volume. A separate, better-architected device
picker (`presentation/main_window.py` + `device_selector.py` +
`application/scanning/device_scanner.py`) existed but was dead code, only
referenced by tests.

**Fix:** added a "Detect Devices" button to the Settings page, using the
(now-fixed) enumeration logic, showing device path/kind/capacity/
removable-status for both Windows and Linux.

**Also added:** real removable-media detection —
`IOCTL_STORAGE_QUERY_PROPERTY` for physical drives, `GetDriveTypeW` for
logical volumes — replacing a hardcoded `False` placeholder.

## 8. Pre-existing, unrelated bug fixed to make testing possible at all

`infrastructure/disk/windows_disk_reader.py` called
`ctypes.windll.kernel32` unconditionally at import time, crashing the
entire module tree (and therefore the whole test suite) on any
non-Windows platform. Guarded behind a platform check so import succeeds
everywhere; actual use of Windows-only calls still fails naturally and
clearly if attempted on a non-Windows platform.

## Self-correction: regressions I introduced, then found and fixed

Running the pre-existing test suite (which I had not done before this
pass) surfaced two real regressions in my own carving-engine rewrite:

1. Footer search was skipping ahead to `min_size` before starting, which
   missed real footers on legitimately-small files. Fixed: search now
   starts immediately after the header.
2. The container-signature sanity check had become an unconditional
   upfront gate, rejecting valid files with minimal-but-real headers
   before footer search even ran. Fixed: it's now only the fallback
   safety net for the genuinely blind "no footer, no structure resolved"
   case, matching the original code's actual intent.

One pre-existing test fixture was also corrected: a 144-byte synthetic
JPEG that is smaller than the signature database's own configured
`min_size=1024` for JPEG. It was only "passing" before because the old
(buggy) code returned a wrong, inflated size guess that happened to clear
the threshold — not because it found the real footer. With footer
detection now actually correct, the undersized result is properly
rejected, and the fixture was padded to a realistic size.

## Known limitations (cannot be solved without substantially more scope)

- **APFS/HFS+ are unimplemented.** They fail honestly rather than fake
  support. Real implementation (APFS copy-on-write B-trees, HFS+ catalog
  B-tree) is a substantial, separate undertaking.
- **Windows-specific code is logically verified but not tested on real
  Windows.** UAC elevation/relaunch, `\\.\PhysicalDriveN` raw access,
  `IOCTL_STORAGE_QUERY_PROPERTY`, `GetDriveTypeW` — all traced and
  written to the documented Win32 API contracts, but this development
  environment is Linux-only and has no Windows machine or physical
  USB/SD hardware to test against, per your own note that live
  hardware/OS testing isn't available here either.
- **EXT4 deleted-file *content* recovery is fundamentally limited by
  ext4 itself**, not this parser: modern ext4 commonly clears a deleted
  inode's size, block count, and extent pointers on unlink (verified
  directly against a real filesystem). When that happens, metadata-based
  recovery cannot reconstruct the file — the parser now says so honestly
  instead of hiding the entry. The carving engine remains the correct
  fallback for such cases, since it finds file data by signature,
  independent of inode state.
- **JPEG (and any simple footer-marker format) is vulnerable to a footer
  byte sequence coincidentally appearing before the true end** — a
  known, industry-wide carving challenge (e.g. an embedded EXIF
  thumbnail with its own end marker), not something introduced or fully
  solved by this patch.
- **MP4/MOV extension labeling and ZIP-family labeling beyond
  docx/xlsx/pptx/zip** (e.g. generic `.zip` vs some other ZIP-based
  format) rely on the signature-list order or heuristic markers and can
  occasionally mislabel the extension — this is cosmetic (the recovered
  bytes/size are correct either way), not a data-loss issue.
- **64-bit block-group-descriptor size** (ext4 `INCOMPAT_64BIT` feature,
  used only on very large volumes) is not supported by the EXT4 parser.
- **htree-indexed directories** (large directories on ext4) are not
  walked past their first data block, to avoid misreading htree index
  metadata as directory entries; typical directories are unaffected.
- **EBML/MKV parsing** handles a leaf level and one level of extent-tree
  indirection for large/heavily fragmented files' index structures, and
  streamed/unknown-size Matroska segments report a capped, unverified
  size rather than a false-confident exact one.
