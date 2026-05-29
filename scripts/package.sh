#!/bin/bash
# Package CyberEval paper for IEEE Access submission
set -e

ZIPNAME="cybereval-ieee-access-$(date +%Y%m%d).zip"
TMPDIR=$(mktemp -d)

echo "Packaging for IEEE Access submission..."

# Copy paper source and figures (no PDF — publisher compiles from source)
cp paper/main.tex "$TMPDIR/"
cp -r paper/figures "$TMPDIR/figures"

# Remove any leftover build artifacts from figures
rm -f "$TMPDIR"/figures/*.aux "$TMPDIR"/figures/*.log

# Optional: add a cover letter if it exists
if [ -f paper/cover-letter.tex ]; then
    cp paper/cover-letter.tex "$TMPDIR/"
    echo "  → cover letter included"
fi

# Create zip
cd "$TMPDIR"
zip -r "$ZIPNAME" . > /dev/null
mv "$ZIPNAME" "$OLDPWD/"
cd "$OLDPWD"
rm -rf "$TMPDIR"

echo "Done: $ZIPNAME ($(du -h "$ZIPNAME" | cut -f1))"
