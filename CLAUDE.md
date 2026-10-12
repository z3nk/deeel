# Meal Deal Finder

Hackathon project: ranks shops near UCL Bloomsbury and builds the best main + snack + drink.
Read PLAN.md first. Read UI_BRIEF.md for the interface.

## Rules
- Python only, SQLite for storage, Streamlit for the UI.
- Do NOT write code until I say "start building". Planning and questions only.
- No scraping. Data comes from in-store photos and a hand-collected seed walk.
- Allergen and diet info comes only from printed label text. Unknown means unsafe.
- Credits are paid only when a record is approved. Pending items are shown but unpaid.
- Never commit .env or the API key.
- Keep the app fast: load the DB once, cache results, call Claude only on button or upload.
