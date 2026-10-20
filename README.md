\# Ever Recover



A Python tool for recovering deleted files from disk images and drives. It has a PyQt6 desktop GUI and a command-line interface. It combines filesystem parsing (to find deleted entries) with signature-based file carving (to find file data when the filesystem records are gone).



> A learning project in digital forensics. Read \[Known limitations](#known-limitations) before relying on it.



\## Demo



I hid a real 49,368-byte JPEG inside an 8 MB disk image of random data and ran a hybrid scan. The tool carved it back out, rated it the only High Confidence result, and recovered it at the same size.



!\[Dashboard after scanning the test image](screenshots/gui-dashboard.png)

!\[Files page](screenshots/gui-files.png)

!\[Recovered photo](screenshots/recovered-photo.png)



The other \~524 results are low-quality matches from the random filler data. On a real disk, expect some noise too, so check the confidence rating.



\## What it does



\- \*\*File carving:\*\* finds files by signature (37 file types, including JPEG, PNG, PDF, Office documents, ZIP, MP4/MOV, AVI, WAV, MKV/WebM, FLV). Sizes come from each format's own structure (RIFF chunks, MP4 boxes, EBML segments, ZIP end-of-central-directory, FLV tags) rather than guesses.

\- \*\*Filesystem parsing:\*\* NTFS and FAT32 parsers, plus a from-scratch ext2/3/4 parser (superblock, block groups, inodes, extent trees, deleted-inode scan).

\- \*\*Confidence ratings:\*\* each result is rated from Excellent down to Low, and the rating drops when a file's size could not be verified.

\- \*\*Reports:\*\* recovery reports with case number and examiner fields (PDF, HTML, CSV, JSON).

\- \*\*Classification:\*\* extension- and entropy-based classification and corruption checks (heuristics, not machine learning).



\## Install



```bash

git clone https://github.com/dreamtokyommii/ever-recover.git

cd ever-recover

pip install -r requirements.txt

```



Python 3.10 or newer.



\## Usage



\*\*Source must be a disk image or a drive.\*\* Pointing the GUI at an ordinary folder only copies files that still exist and cannot recover deleted ones.



GUI:



```bash

python ever\_recover.py

```



Open \*\*Settings\*\*, choose a disk image as the source (click \*\*Browse\*\*, cancel the folder dialog, then pick the image file in the second dialog), pick an existing output folder on a \*different\* drive, click \*\*Apply Settings\*\*, then run the scan from the \*\*Dashboard\*\*.



CLI (run from the project folder):



```bash

python -m cli.cli scan disk.img -o out/

python -m cli.cli recover disk.img -o out/ --all

python -m cli.cli report disk.img -o out/ --case CASE-001 --examiner "Your Name"

```



Only use it on disks and images you own or are authorised to examine.



\## Tests



```bash

python -m pytest tests/ -v

```



Regression tests include byte-exact (SHA-256) recovery of carved JPEG, AVI and MP4 files, including headers that straddle read-chunk boundaries, and recovery from a real `mkfs.ext4` image (skipped if `mkfs.ext4` or root is unavailable). GUI tests need PyQt6. One test that exercises a Windows-only device path fails when run on Linux.



\## Known limitations



\- APFS and HFS+ are not implemented; they report an error instead of pretending to scan.

\- The Windows drive-access code (UAC elevation, `\\\\.\\PhysicalDriveN`, removable-drive detection) has not been tested on real hardware. Test on disk images first.

\- On ext4, deleted files often have their size and extent pointers cleared by the filesystem, so metadata recovery can fail and carving is the fallback.

\- Footer-based carving (e.g. JPEG) can be fooled by an embedded thumbnail's end marker.

\- ext4 64-bit block group descriptors and large indexed (htree) directories are not supported.

\- Carving random or heavily compressed data produces many false positives.



More detail: \[CHANGES\_AND\_LIMITATIONS.md](CHANGES\_AND\_LIMITATIONS.md).



\## Licence



MIT. See \[LICENSE](LICENSE).

