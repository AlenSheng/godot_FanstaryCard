# PR13 B08.4 cloud runtime recovery (S0)

The missing volatile runtime was rebuilt on Tencent cloud from fixed b042 source. The 372-file source subset matches both Git and the original input hashes; 1,696 old package/build artifacts are explicitly excluded. The complete package cache was mounted read-only. All eight rebuilt runtime files exactly match their original SHA-256 values. The 56 required domain regressions passed with zero skips.

All 969 recovery members were streamed to G and verified by archive/member SHA and gzip CRC. The passed temporary build scratch was then removed; the persistent source and runtime remain for continuation.

This restores the executor, not the missing raw evidence. Original full-run metadata records 88 completed native units, but only 87 have verified G raw backups (174,000 encounters). Mage-E1-Water-L5-B0 requires a separate named recovery attempt with the original 1,000 paired seeds. The 720,000-encounter experiment and MAIN acceptance remain pending.
