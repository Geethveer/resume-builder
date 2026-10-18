#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
python workflow_reference.py \
 --candidate examples/candidate.json \
 --job examples/job.json \
 --employer examples/employer_evidence.json \
 --policy config/pipeline_policy.json \
 --output out/assessment.json
printf 'Saved to out/assessment.json\n'
