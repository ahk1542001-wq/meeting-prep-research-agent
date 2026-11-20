#!/bin/bash
# The exact session recorded for the demo: a real live run of the
# agent, then a walk through the brief it produced, section by
# section. Everything on screen is real output of the commands
# shown — nothing is staged or generated.
cd "$(dirname "$0")"
echo "$ python agent.py \"Tavily\" --context \"API partnership call\""
sleep 1
python3 agent.py "Tavily" --context "API partnership call" --out brief-demo.md
sleep 2
echo
echo "$ # what the agent found — snapshot:"
sleep 1
awk '/^## Snapshot/,/^## Recent/' brief-demo.md | head -n -1
sleep 8
echo
echo "$ # recent developments (last month):"
sleep 1
awk '/^## Recent/,/^## Key people/' brief-demo.md | head -n -1
sleep 10
echo
echo "$ # key people:"
sleep 1
awk '/^## Key people/,/^## Source/' brief-demo.md | head -n -1
sleep 7
echo
echo "$ # and the end of the brief — questions to ask:"
sleep 1
sed -n '/## Questions/,$p' brief-demo.md
sleep 9
echo
echo "$ # done — the full brief is saved in brief-demo.md, sources included."
sleep 3
