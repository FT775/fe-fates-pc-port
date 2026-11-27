# Public release notes

One file per public Vanilla+ release: `<tag>-vanilla.md` (for example `r86-vanilla.md`), written for strangers.

- `tools/release/package.py build --edition vanilla` uses the file for its tag word for word as `RELEASE_NOTES.md`
  (the text on the GitHub release page). Without a file for the tag, the notes are made from the round reports.
- The package checks still read it: the full credit line of CREDITS.md (one line only), no private strings, no
  game bytes. It must name the last public release (`last_public_tag` in `config/release/editions.json`).
- `SHA256SUMS.txt` lists it next to the zip.
- Changing the words after the owner read them: commit without a new round report, then run
  `python tools/release/package.py build --edition vanilla --tag <tag>` and `python tools/release/package.py markers`.

docs/RELEASE.md ("The public notes file") has the whole flow.
