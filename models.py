"""
Frozen Pydantic schema for Meal Deal Finder.
Do NOT modify this file without agreement from the whole team.
All three record types (Shop, Deal, Item) plus User, CreditEvent, Reward.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enums / literals
# ---------------------------------------------------------------------------

Chain = Literal["tesco", "sainsburys", "waitrose", "marks-and-spencer", "lidl", "pret"]
Category = Literal["main", "snack", "drink"]
Temperature = Literal["hot", "cold", "ambient"]
Status = Literal["pending", "approved", "rejected"]
Confidence = Literal["high", "medium", "low"]
SubmittedVia = Literal["seed", "upload"]
LoyaltyScheme = Literal["Clubcard", "Nectar", "other"]
DealName = Literal["Meal Deal", "Premium Meal Deal"]
Sort = Literal["quality", "distance", "price"]
TemperaturePref = Literal["any", "hot", "cold"]
CreditType = Literal["earn", "spend", "reversal"]
CreditReason = Literal[
    "approved_item",
    "approved_deal",
    "stale_bonus",
    "coverage_bonus",
    "confirmation",
    "reward_redeemed",
    "reversal",
]


# ---------------------------------------------------------------------------
# Shop
# ---------------------------------------------------------------------------

class Shop(BaseModel):
    shop_id: str                        # e.g. "tesco-tcr"
    chain: Chain
    name: str
    address: str
    walking_minutes: float              # measured by hand from campus origin
    last_verified: date
    lat: float                          # WGS84 latitude
    lng: float                          # WGS84 longitude

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Deal  (a bundle price over main + snack + drink)
# ---------------------------------------------------------------------------

class Deal(BaseModel):
    deal_id: str
    shop_id: str
    name: DealName
    price_gbp: float
    loyalty_price_gbp: Optional[float] = None
    loyalty_scheme: Optional[LoyaltyScheme] = None
    source_image: str                   # filename in seed/ or uploads/
    last_seen: date
    submitted_by: Optional[str] = None  # user_id; null for seed photos
    status: Status = "pending"

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------

class Item(BaseModel):
    item_id: str
    shop_id: str
    name: str
    category: Category
    price_gbp: float
    loyalty_price_gbp: Optional[float] = None
    meal_deal_eligible: Optional[bool] = None   # null = unknown
    temperature: Temperature
    diet_flags: List[str] = Field(default_factory=list)   # only from label text
    allergens: List[str] = Field(default_factory=list)    # only from label text
    ingredients_text: Optional[str] = None
    # Meat/fish named on the label (name or ingredients). [] = none; None = unknown
    meats: Optional[List[str]] = None
    # Per pack, from the printed nutrition panel. None = not on label / unreadable
    kcal: Optional[float] = None
    protein_g: Optional[float] = None
    premium_range: Optional[bool] = None
    quality_rating: Optional[float] = None      # 1–5, from student ratings only
    source_image: str
    source_text: str                             # label wording for price/diet/allergens
    last_seen: date
    submitted_via: SubmittedVia
    submitted_by: Optional[str] = None
    status: Status = "pending"
    confidence: Confidence = "high"
    needs_review: bool = False

    @model_validator(mode="after")
    def flag_low_confidence(self) -> "Item":
        if self.confidence in ("medium", "low"):
            # Can't mutate a frozen model — validation only; caller must set needs_review
            pass
        return self

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# User (minimal — handle + reputation only)
# ---------------------------------------------------------------------------

class User(BaseModel):
    user_id: str
    handle: str
    reputation: float = 1.0             # 1.0–1.5 multiplier

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Credit ledger (append-only)
# ---------------------------------------------------------------------------

class CreditEvent(BaseModel):
    event_id: str
    user_id: str
    type: CreditType
    credits: int                        # positive = earn; negative = spend/reversal
    reason: CreditReason
    ref_id: str                         # item_id or reward_id
    created_at: datetime

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Reward
# ---------------------------------------------------------------------------

class Reward(BaseModel):
    reward_id: str
    sponsor: str
    title: str
    cost_credits: int
    codes_remaining: int
    expires: Optional[date] = None

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Optimiser output types (not persisted — used in memory only)
# ---------------------------------------------------------------------------

class Lunch(BaseModel):
    """Best main + snack + drink for one shop under one pricing mode."""
    shop: Shop
    main: Item
    snack: Item
    drink: Item
    price_gbp: float
    used_deal: bool
    deal: Optional[Deal] = None
    score: float
    why: str = ""                       # filled by Claude after ranking

    model_config = {"frozen": False}    # mutable so 'why' can be set post-ranking


class Preferences(BaseModel):
    """Set from sidebar controls: sliders, chips, toggles, sort dropdown."""
    # Sort dropdown → maps to score weights in optimiser
    sort: Sort = "quality"
    # Hot/cold/any segmented control
    temperature_pref: TemperaturePref = "any"
    # Price and walking controls
    max_price_gbp: Optional[float] = None
    max_walking_minutes: float = 10.0
    # Diet and allergen chips
    diet_flags: List[str] = Field(default_factory=list)
    allergens_exclude: List[str] = Field(default_factory=list)
    # Meat multiselect: allowed meats for the main ("none" = meat-free). Empty = any
    meats_allowed: List[str] = Field(default_factory=list)
    # Nutrition, whole meal (main + snack + drink). None = no limit
    min_protein_g: Optional[float] = None
    max_kcal: Optional[float] = None
    # Loyalty card toggle
    has_clubcard: bool = False
    has_nectar: bool = False

    model_config = {"frozen": True}
