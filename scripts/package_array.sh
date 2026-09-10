#!/bin/bash
# Package CyberEval paper LaTeX source for Elsevier Array submission.
# The unmarked (clean) manuscript is uploaded as an editable source package:
# main.tex + references.bib + the figure PDFs actually referenced in the paper.
# No compiled PDF is included — the publisher compiles from source.
set -e

ZIPNAME="cybereval-array-$(date +%Y%m%d).zip"
TMPDIR=$(mktemp -d)

echo "Packaging for Elsevier Array submission..."

# Verify every figure referenced in main.tex exists before packaging
while read -r fig; do
    [ -f "paper/$fig" ] || { echo "MISSING figure: $fig" >&2; exit 1; }
done < <(grep -oE 'figures/[A-Za-z0-9_./-]+\.(pdf|png)' paper/main.tex | sort -u)

cp paper/main.tex "$TMPDIR/"
cp paper/references.bib "$TMPDIR/"
mkdir -p "$TMPDIR/figures"
# Only the figures actually referenced (pdf forms used by the manuscript)
grep -oE 'figures/[A-Za-z0-9_./-]+\.pdf' paper/main.tex | sort -u | while read -r fig; do
    cp "paper/$fig" "$TMPDIR/$fig"
done

# Sanity: exactly the files LaTeX needs
cd "$TMPDIR"
zip -r "$ZIPNAME" . > /dev/null
mv "$ZIPNAME" "$OLDPWD/"
cd "$OLDPWD"
rm -rf "$TMPDIR"

echo "Done: $ZIPNAME ($(du -h "$ZIPNAME" | cut -f1))"
unzip -l "$ZIPNAME"
