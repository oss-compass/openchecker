# Script download pinning

The `pinned-dependencies-checker` script collector recognizes a download pin from:

- A full 40-character commit ID in an HTTPS GitHub raw-file or source-archive URL
  (`raw.githubusercontent.com`, `github.com/.../raw/...`,
  `github.com/.../archive/...`, or `codeload.github.com`).
- A `pip install` URL with one complete hexadecimal `sha256`, `sha384`, or
  `sha512` hash fragment. Pip verifies these fragments; curl and wget do not.

Words such as `shared`, `tags`, `commit`, or `version` in a URL do not establish a
pin. Branches, version tags, shortened commit IDs, arbitrary hash-looking path
components, and malformed hash fragments remain unpinned. Other URL layouts
remain unpinned until a supported immutable-reference rule is available.

This is static inspection of the URLs found by the existing line-based script
collector. It does not follow redirects, run downloads, inspect lockfiles for
script URLs, or infer verification from separate shell checksum commands.

References: [Scorecard pinning criteria](https://github.com/ossf/scorecard/blob/main/docs/checks.md#pinned-dependencies),
[GitHub permanent file links](https://docs.github.com/en/repositories/working-with-files/using-files/getting-permanent-links-to-files),
and [pip URL hash verification](https://pip.pypa.io/en/stable/topics/secure-installs/#using-hashes-from-pypi-or-other-index-servers).
