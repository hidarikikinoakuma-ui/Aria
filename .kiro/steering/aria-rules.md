---
inclusion: always
---

# ARIA Project Rules

## Player
- Name: Hidarikikinoaku (LeftHandDevil)
- Rank: Gold 4 → Predator
- Legend: Alter
- Controller: GameSir G7 Pro 8K

## Coach
- Name: Aria (@migikonokami / RightHandGod)
- Personality: firm like Erza Scarlet, loyal like Rem

## Main File
- Everything lives in `ARIA_ALL_IN_ONE.py` — do not split into modules unless asked
- Always read this file before editing it
- Always syntax-check after editing: `python3 -c "import ast; ast.parse(open('ARIA_ALL_IN_ONE.py').read()); print('Syntax OK')"`
- Always commit and push after completing a task

## Design Rules (do not override without asking)
- Live API is primary event source — OCR is fallback only
- Zero performance impact during matches — all processing happens post-match
- Cosplay mode activates at overall_score >= 9.0
- Social posts go out as @migikonokami
- YouTube uploads every Sunday at 20:00 automatically
- Mobile companion is a PWA — no app store

## Repo
- GitHub: https://github.com/hidarikikinoakuma-ui/Aria
- Branch: main
- Push after every completed task

## Communication Style
- Keep responses short and direct
- Never ask the user to re-explain the project
- When user says "push it" or "send it" — commit and push immediately
