"""Transparent hybrid recommender: hard rule filters -> text/preference scoring -> ranking.

Hard filters (never relaxed): active product, at least one in-stock variant, budget.
Relaxed in order when nothing matches: size, then category.
Soft signals (weights below): keyword/tag/name text match, colour, brand, fashion-profile preferences, sale.
Every result carries human-readable `reasons` derived from real catalogue facts.
"""
import re
from dataclasses import dataclass, field

from sqlalchemy import and_

from ..models import Category, FashionProfile, Product, ProductVariant

W_NAME, W_TAG, W_CATEGORY, W_BRAND_TEXT, W_DESC = 2.0, 2.0, 1.5, 1.5, 0.5
W_COLOR, W_BRAND_REQ, W_BRAND_PROFILE = 2.0, 3.0, 1.0
W_PROFILE_STYLE, W_PROFILE_COLOR, W_PROFILE_CATEGORY, W_PROFILE_BUDGET, W_SALE = 1.0, 0.5, 1.0, 0.5, 0.3

_TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a", "an", "the", "for", "and", "or", "to", "of", "in", "on", "with", "me", "my", "i", "need", "want", "some",
    "suggest", "find", "show", "please", "outfit", "outfits", "look", "looks", "wear", "something", "that", "match",
    "matches", "what", "which", "can", "you", "is", "are", "under", "below", "above", "around", "about", "good",
    "best", "nice", "new", "get", "buy", "idea", "ideas", "help", "event", "any", "this", "these", "those", "it",
}


def tokens(text):
    out = []
    for t in _TOKEN.findall((text or "").lower()):
        if t in STOPWORDS or len(t) < 2:
            continue
        out.append(t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t)
    return out


@dataclass
class SearchSpec:
    keywords: list = field(default_factory=list)
    category: str = ""
    min_price_minor: int = 0
    max_price_minor: int = 0
    colors: list = field(default_factory=list)
    sizes: list = field(default_factory=list)
    brands: list = field(default_factory=list)
    occasion: str = ""
    styles: list = field(default_factory=list)
    outfit: bool = False

    def query_terms(self):
        terms = []
        for src in (self.keywords, [self.occasion], self.styles):
            for s in src:
                terms.extend(tokens(s))
        return list(dict.fromkeys(terms))


@dataclass
class Ranked:
    product: Product
    score: float
    reasons: list
    relevance: float


def _norm(s):
    return (s or "").strip().lower()


def find_category(name):
    """Resolve a category name (case-insensitive) to the category and its children's ids."""
    if not name:
        return None, []
    want = _norm(name)
    for c in Category.query.filter_by(is_active=True):
        if _norm(c.name) == want or _norm(c.name).rstrip("s") == want.rstrip("s"):
            kids = [k.id for k in Category.query.filter_by(parent_id=c.id)]
            return c, [c.id, *kids]
    return None, []


def profile_for(user_id):
    return FashionProfile.query.filter_by(user_id=user_id).first() if user_id else None


def _score(p, spec, profile, terms):
    reasons, relevance, pref = [], 0.0, 0.0
    name_t, tag_t = set(tokens(p.name)), set(tokens(" ".join(p.tags or [])))
    cat_t = set(tokens(p.category.name if p.category else ""))
    brand_t, desc_t = set(tokens(p.brand or "")), set(tokens(p.description or ""))

    matched_tags = []
    for t in terms:
        if t in tag_t:
            relevance += W_TAG
            matched_tags.append(t)
        elif t in name_t:
            relevance += W_NAME
        elif t in cat_t:
            relevance += W_CATEGORY
        elif t in brand_t:
            relevance += W_BRAND_TEXT
        elif t in desc_t:
            relevance += W_DESC
    if matched_tags:
        reasons.append("Tagged " + ", ".join(sorted(set(matched_tags))))

    in_stock_colors = {_norm(v.color) for v in p.variants if v.stock_quantity > 0 and v.color}
    for c in spec.colors:
        if _norm(c) in in_stock_colors:
            relevance += W_COLOR
            reasons.append(f"Available in {c}")
    if p.brand and _norm(p.brand) in {_norm(b) for b in spec.brands}:
        relevance += W_BRAND_REQ
        reasons.append(f"From {p.brand}")

    if profile:
        styles = {_norm(s) for s in (profile.preferred_styles or [])}
        hit = sorted(styles & {_norm(t) for t in (p.tags or [])})
        if hit:
            pref += min(2, len(hit)) * W_PROFILE_STYLE
            reasons.append("Matches your style: " + ", ".join(hit))
        if in_stock_colors & {_norm(c) for c in (profile.preferred_colors or [])}:
            pref += W_PROFILE_COLOR
            reasons.append("In a colour you like")
        if p.brand and _norm(p.brand) in {_norm(b) for b in (profile.preferred_brands or [])}:
            pref += W_BRAND_PROFILE
            reasons.append(f"A brand you like ({p.brand})")
        if p.category and _norm(p.category.name) in {_norm(c) for c in (profile.preferred_categories or [])}:
            pref += W_PROFILE_CATEGORY
        lo, hi = profile.budget_min_minor, profile.budget_max_minor
        if hi and p.effective_price_minor <= hi and (not lo or p.effective_price_minor >= lo):
            pref += W_PROFILE_BUDGET
    if p.effective_price_minor < p.price_minor:
        pref += W_SALE
        reasons.append("On sale")
    return relevance, pref, reasons


def _candidates(spec, cat_ids, use_sizes):
    q = Product.query.filter(Product.status == "active")
    if cat_ids:
        q = q.filter(Product.category_id.in_(cat_ids))
    vcond = [ProductVariant.stock_quantity > 0]
    if use_sizes and spec.sizes:
        vcond.append(ProductVariant.size.in_(spec.sizes))
    q = q.filter(Product.variants.any(and_(*vcond)))
    rows = q.all()
    if spec.max_price_minor:
        rows = [p for p in rows if p.effective_price_minor <= spec.max_price_minor]
    if spec.min_price_minor:
        rows = [p for p in rows if p.effective_price_minor >= spec.min_price_minor]
    return rows


def recommend(spec, user_id=None, limit=8):
    """Returns (ranked list, relaxed notes). All products are real, active and in stock."""
    profile = profile_for(user_id)
    terms = spec.query_terms()
    cat, cat_ids = find_category(spec.category)
    relaxed = []

    rows = _candidates(spec, cat_ids, use_sizes=True)
    if not rows and spec.sizes:
        rows = _candidates(spec, cat_ids, use_sizes=False)
        relaxed.append("size")
    if not rows and cat_ids:
        rows = _candidates(spec, [], use_sizes=False)
        relaxed.append("category")

    ranked = []
    for p in rows:
        relevance, pref, reasons = _score(p, spec, profile, terms)
        ranked.append(Ranked(p, relevance + pref, reasons, relevance))

    has_query = bool(terms or spec.colors or spec.brands)
    if has_query and any(r.relevance > 0 for r in ranked):
        ranked = [r for r in ranked if r.relevance > 0]
    ranked.sort(key=lambda r: (-r.score, -r.product.id))

    if spec.outfit:  # complete outfit: best item per category first, then the rest
        seen, first, rest = set(), [], []
        for r in ranked:
            (rest if r.product.category_id in seen else first).append(r)
            seen.add(r.product.category_id)
        ranked = first + rest
    return ranked[:limit], relaxed
