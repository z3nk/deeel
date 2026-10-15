A toggle chip that excludes an allergen; the first control in the filters, styled in serious mode.

Hand-written from the `app.py` sidebar and the briefs.

- Chips: Gluten, Milk, Egg, Nuts, Sesame, Soy, Fish, Shellfish, under the heading "Allergies — avoid" in `allergen-ink`.
- Off: `surface` with a `border-strong` outline and the allergen name. On: `allergen` fill, `on-primary` text, label "No {Allergen} ✕".
- When any chip is on, show "Items with unchecked labels are hidden." in `small`.
- Always first in the controls. On a 390px screen it must be reachable in one tap from the results (top filter bar or the first block of the Filters sheet).
- No stickers, emoji jokes or display type here.

The consumer provides: the allergen list and the selected set. Streamlit: `st.pills(selection_mode="multi")` or styled `st.button`s.
