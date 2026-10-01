#!/bin/bash
# Versioned reproducibility release for ARRAY-D-26-02880 round 2.
# Packages everything a reviewer needs to re-derive every number in the paper:
#   - the 250-item balanced question bank + balance provenance
#   - the validated re-measurement trace (2,000 calls, complete capture)
#   - the original protocol trace (provenance)
#   - the adjudication docket and validated answer set
#   - the scripts that reproduce the run, the analyses, and the figures
#   - release notes (protocol, dates, served models)
set -e

RELEASE="cybereval-array-release-$(date +%Y%m%d)"
TMPDIR=$(mktemp -d)
ROOT=$(cd "$(dirname "$0")/.." && pwd)

mkdir -p "$TMPDIR/$RELEASE/data/round2_validated" \
         "$TMPDIR/$RELEASE/data/original_protocol_run" \
         "$TMPDIR/$RELEASE/scripts"

# Bank + balance provenance
cp "$ROOT/experiments/results/question_bank.json" "$TMPDIR/$RELEASE/data/"
cp "$ROOT/experiments/results/bank_balance_provenance.json" "$TMPDIR/$RELEASE/data/"

# Validated re-measurement (single-day, complete capture)
cp "$ROOT/experiments/results/round2_validated/full_run.jsonl" "$TMPDIR/$RELEASE/data/round2_validated/"
cp "$ROOT/experiments/results/round2_validated/docket.jsonl" "$TMPDIR/$RELEASE/data/round2_validated/"
cp "$ROOT/experiments/results/round2_validated/validated_answers.json" "$TMPDIR/$RELEASE/data/round2_validated/"
cp "$ROOT/experiments/results/round2_validated/summary.txt" "$TMPDIR/$RELEASE/data/round2_validated/"
cp "$ROOT/experiments/results/round2_validated/simulation_recalibration.json" "$TMPDIR/$RELEASE/data/round2_validated/"
cp "$ROOT/experiments/results/round2_validated/item_stats.json" "$TMPDIR/$RELEASE/data/round2_validated/"

# Original protocol run (provenance)
cp "$ROOT/experiments/results/live_mcq/v2_results.jsonl" "$TMPDIR/$RELEASE/data/original_protocol_run/"
cp "$ROOT/experiments/results/live_mcq/v2_max50_provenance.jsonl" "$TMPDIR/$RELEASE/data/original_protocol_run/"

# Scripts
cp "$ROOT/experiments/run_full_recapture.py" "$TMPDIR/$RELEASE/scripts/"
cp "$ROOT/experiments/analyze_validated.py" "$TMPDIR/$RELEASE/scripts/"
cp "$ROOT/experiments/make_round2_figures.py" "$TMPDIR/$RELEASE/scripts/"
cp "$ROOT/experiments/analyze_revision_v2.py" "$TMPDIR/$RELEASE/scripts/"
cp "$ROOT/experiments/run_live_mcq_v2.py" "$TMPDIR/$RELEASE/scripts/"
cp "$ROOT/experiments/simulation_recalibration_validated.py" "$TMPDIR/$RELEASE/scripts/"
cp "$ROOT/experiments/run_real_evaluation.py" "$TMPDIR/$RELEASE/scripts/"

# Release notes
cp "$ROOT/scripts/RELEASE_NOTES.md" "$TMPDIR/$RELEASE/RELEASE_NOTES.md"

cd "$TMPDIR"
zip -r "$RELEASE.zip" "$RELEASE" > /dev/null
mv "$RELEASE.zip" "$ROOT/"
cd "$ROOT"
rm -rf "$TMPDIR"

echo "Done: $RELEASE.zip ($(du -h "$RELEASE.zip" | cut -f1))"
unzip -l "$RELEASE.zip" | head -30
