# Shop images

Added by hand only, never scraped or fetched at runtime (see `shop_images.py`).

- `logos/<chain>.png|svg|jpg|webp`: chain logo, e.g. `logos/tesco.png`.
  Chain keys: tesco, sainsburys, waitrose, marks-and-spencer, lidl, pret.
- `shops/<shop_id>.jpg|png|webp`: storefront photo of that branch from the seed walk,
  e.g. `shops/tesco-tcr.jpg`. Shown as a banner on the shop page.

With no file, a badge in the chain's brand colour is shown instead.
