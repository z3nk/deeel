A toggle chip for diet filters (Vegetarian, Vegan, Halal, Kosher).

Hand-written from the `app.py` sidebar.

- Off: `surface` with a `border-strong` outline. On: `primary` fill, `on-primary` text, a ✓ after the label.
- An AND filter: every selected flag must be true. Below Halal/Kosher show "Only mains with a printed halal/kosher label" in `small`.
- Meat pills (Chicken, Beef, Pork, Lamb, Turkey, Duck, Fish; none = any) use the same style.

The consumer provides: the options and the selected set. Streamlit: `st.pills(selection_mode="multi")`.
