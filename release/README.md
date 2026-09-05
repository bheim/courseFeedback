# Legacy Chrome extension release

This directory preserves the public, extension-only product as a separate
release layer. The source remains unchanged in `courseFeedbackLaunch/`; the
baseline records the exact version 3.0 bytes at Git commit
`0f53d31b35c8a5ca527048048c962c33d6b312da` and Chrome Web Store ID
`fhmmbigjknknbmejcjbnkjjpfkbkndim`.
The baseline's `git_tree` is the tree object for the `courseFeedbackLaunch/`
subdirectory at that commit, rather than the repository's root tree.

The corresponding public listing is the
[Course Feedback Extension in the Chrome Web Store](https://chromewebstore.google.com/detail/course-feedback-extension/fhmmbigjknknbmejcjbnkjjpfkbkndim).

Build a release ZIP from the repository root:

```bash
python3 release/package_legacy_extension.py
```

The packager verifies every source file's size and SHA-256 hash before it
writes `release/dist/course-feedback-extension-v3.0.zip`. It packages only
the baseline's explicit allowlist, rejects missing or unexpected files,
symlinks and unsafe paths, and refuses common credential or raw-database
formats even if somebody adds one to a future allowlist. ZIP members are
stored without compression, sorted, and carry fixed timestamps and
permissions, so identical inputs produce identical ZIP bytes independent of
the installed zlib version.

Run its tests with:

```bash
python3 -m unittest tests.test_legacy_extension_release
```

When the public extension intentionally changes, create a new versioned
baseline after reviewing the complete source tree. Do not overwrite this
v3.0 baseline; retaining it makes the original public product reproducible.
