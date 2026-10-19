# Ever Recover Validation Test Plan

All tests use a mounted test image or a byte-for-byte working copy. The source
reader must be opened read-only and a hash of the source is recorded before
and after each run.

| Dataset | Expected result |
| --- | --- |
| Live folder with nested files | Every item is `copy_only`; zero recovered items |
| NTFS image with deleted resident file | Filename, MFT record, timestamps and complete resident bytes recovered |
| NTFS image with deleted contiguous file | Complete non-resident data recovered from its runlist |
| NTFS image with deleted fragmented file | All runs reconstructed in VCN order |
| NTFS image with overwritten run | `partially_recovered` or `unrecoverable`, never full |
| Mixed active/deleted image | Active records are not reported as deleted recovery |
| Empty, malformed or unsupported source | Explicit error and no recovery-success claim |
| Read-only device without access | Elevation/access error and no source writes |

For each dataset, verify output bytes against the known ground truth, compare
source hashes, inspect the JSON and CSV audit records, and record counts for
`copy_only`, `fully_recovered`, `partially_recovered`, and `unrecoverable`.