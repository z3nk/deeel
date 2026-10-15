A coloured initials square that stands in for a supermarket chain; chain logos are never used.

Hand-written from `shop_images.py` (`_BADGES`, `logo_html`).

| Chain | Text | Fill | Ink |
|---|---|---|---|
| Tesco | T | `shop-tesco` | `on-shop-light` |
| Sainsbury's | S | `shop-sainsburys` | `on-shop-dark` |
| M&S | M&S (smaller text) | `shop-marks-and-spencer` | `on-shop-light` |
| Lidl | L | `shop-lidl` | `on-shop-lidl` |
| Waitrose | W | `shop-waitrose` | `on-shop-light` |
| Pret | P | `shop-pret` | `on-shop-light` |
| unknown | first letter | `shop-fallback` | `text` |

- 28px square, `radius-badge`. Always next to the shop name in text; give it `aria-label` = the shop name when it stands alone.
- Sainsbury's uses dark ink: white on its orange failed (3.07:1).
- In-app only. Marketing must not use supermarket logos; badges are allowed in app screenshots.
