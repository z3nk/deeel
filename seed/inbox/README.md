# Photo inbox

Drop photos into `<shop>/<general|main|snack|drink>/` (on GitHub: open the folder → **Add file → Upload files**).

| Folder | Shop |
|---|---|
| `tesco-tcr` | Tesco Express |
| `sainsburys-warren-st` | Sainsbury's Local (Warren Street, 21 Hampstead Road) |
| `ms-tcr` | M&S Food |
| `lidl-tcr` | Lidl |
| `waitrose-brunswick` | Waitrose |
| `pret-tcr` | Pret A Manger |

`general` = storefront, meal deal sign, mixed shelf · `main` / `snack` / `drink` = only that type is read.

Then someone pulls and runs `python seed/load_seed.py --inbox`. Everything lands in the Review queue as pending.

**This repo is public.** Photos here are visible to anyone and stay in git history.
**Before committing photos from a computer, run `python seed/load_seed.py --strip-gps`** — it removes GPS from every inbox photo without changing the image or its date.
When uploading through the GitHub website that isn't possible, so instead: turn off location for the photos (iPhone share sheet → Options → Location off,
or Settings → Privacy → Location Services → Camera → Never), and avoid people's faces.
