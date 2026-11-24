"""Dev seed: admin user, categories, sample products. Run: python seed.py  (idempotent)."""
import os

from app import create_app
from app.extensions import db
from datetime import datetime, timedelta

from app.models import (Category, CreditPack, Product, ProductImage, ProductVariant, RewardOffer, Stylist, StylistAvailability,
                        SubscriptionPlan, User)

ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "AdminPass123")

CATS = ["Tops", "Bottoms", "Dresses", "Ethnic", "Footwear", "Accessories"]
# name, category, brand, price INR, sale INR|None, colors, sizes, tags
PRODUCTS = [
    ("Oxford Cotton Shirt", "Tops", "Northwind", 1799, 1499, ["white", "blue"], ["S", "M", "L", "XL"], ["formal", "office"]),
    ("Graphic Streetwear Tee", "Tops", "Urbanite", 999, None, ["black", "grey"], ["S", "M", "L"], ["streetwear", "casual"]),
    ("Slim Fit Chinos", "Bottoms", "Northwind", 1999, None, ["beige", "navy"], ["30", "32", "34"], ["formal", "casual"]),
    ("Relaxed Denim Jeans", "Bottoms", "Urbanite", 2499, 1999, ["blue", "black"], ["30", "32", "34", "36"], ["casual", "weekend"]),
    ("Floral Midi Dress", "Dresses", "Aurelia", 2799, 2299, ["red", "green"], ["S", "M", "L"], ["party", "college"]),
    ("Linen Wrap Dress", "Dresses", "Aurelia", 3299, None, ["beige"], ["S", "M", "L"], ["summer", "brunch"]),
    ("Embroidered Kurta", "Ethnic", "Saanvi", 2199, None, ["maroon", "mustard"], ["S", "M", "L", "XL"], ["ethnic", "festive", "college"]),
    ("Silk Blend Saree", "Ethnic", "Saanvi", 5999, 4999, ["teal", "maroon"], ["Free"], ["ethnic", "wedding"]),
    ("Leather Derby Shoes", "Footwear", "Northwind", 3999, None, ["brown", "black"], ["7", "8", "9", "10"], ["formal", "interview"]),
    ("Minimal White Sneakers", "Footwear", "Urbanite", 2999, 2499, ["white"], ["7", "8", "9", "10"], ["casual", "minimalist"]),
    ("Canvas Tote Bag", "Accessories", "Urbanite", 799, None, ["black", "beige"], ["One size"], ["casual", "college"]),
    ("Woven Leather Belt", "Accessories", "Northwind", 1199, None, ["brown", "black"], ["M", "L"], ["formal"]),
]

# PLACEHOLDER pricing for the open business decisions - edit freely (admin API / this file).
PACKS = [("Starter", 50, 19900), ("Plus", 150, 49900), ("Pro", 400, 99900)]
PLANS = [  # name, description, price INR, interval, credits, frequency, benefits
    ("Stylist Plus", "100 Super Credits with every monthly renewal.", 499, "month", 100, "renewal",
     ["Credits never expire"]),
    ("Stylist Pro", "20 Super Credits every day while subscribed.", 999, "month", 20, "daily",
     ["Credits accumulate and never expire"]),
]

STYLIST_EMAIL, STYLIST_PASSWORD = "stylist@example.com", "StylistPass123"
STYLISTS = [  # name, email, bio, expertise, languages
    ("Stella Rao", STYLIST_EMAIL, "Editorial and wedding stylist with ten years of experience.", ["formal", "wedding", "ethnic"], ["English", "Hindi"]),
    ("Mira Shah", "mira@example.com", "Streetwear and college-wardrobe specialist.", ["streetwear", "casual"], ["English", "Gujarati"]),
]

app = create_app()
with app.app_context():
    if not User.query.filter_by(email=ADMIN_EMAIL).first():
        u = User(name="Admin", email=ADMIN_EMAIL, role="admin", is_verified=True)
        u.set_password(ADMIN_PASSWORD)
        db.session.add(u)
        print(f"Created admin {ADMIN_EMAIL} / {ADMIN_PASSWORD}  (dev only - change it)")
    cats = {}
    for name in CATS:
        c = Category.query.filter_by(name=name).first() or Category(name=name)
        db.session.add(c)
        cats[name] = c
    db.session.flush()
    for i, (name, cat, brand, price, sale, colors, sizes, tags) in enumerate(PRODUCTS, 1):
        if Product.query.filter_by(name=name).first():
            continue
        p = Product(name=name, category_id=cats[cat].id, brand=brand, price_minor=price * 100,
                    sale_price_minor=sale * 100 if sale else None, tags=tags,
                    description=f"{name} by {brand}. A wardrobe staple for {', '.join(tags)} looks.",
                    material="Cotton blend", care="Machine wash cold")
        p.images = [ProductImage(image_url=f"https://picsum.photos/seed/aifp{i}/600/800", alt_text=name, display_order=0)]
        for c in colors:
            for s in sizes:
                p.variants.append(ProductVariant(sku=f"P{i:03d}-{c[:3].upper()}-{s}".replace(" ", ""), size=s, color=c,
                                                 stock_quantity=8 if (i + len(s)) % 5 else 0))
        db.session.add(p)
    for name, credits, price in PACKS:
        if not CreditPack.query.filter_by(name=name).first():
            db.session.add(CreditPack(name=name, credits=credits, price_minor=price))
    for name, desc, price, interval, credits, freq, benefits in PLANS:
        if not SubscriptionPlan.query.filter_by(name=name).first():
            db.session.add(SubscriptionPlan(name=name, description=desc, price_minor=price * 100, billing_interval=interval,
                                            super_credit_amount=credits, grant_frequency=freq, benefits=benefits))
    if not RewardOffer.query.first():
        db.session.add(RewardOffer(name="10 Super Credits", points_cost=100, super_credits=10))
    for name, email, bio, expertise, languages in STYLISTS:
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(name=name, email=email, role="stylist", is_verified=True)
            user.set_password(STYLIST_PASSWORD)
            db.session.add(user)
            db.session.flush()
            print(f"Created stylist {email} / {STYLIST_PASSWORD}  (dev only)")
        sty = Stylist.query.filter_by(user_id=user.id).first()
        if not sty:
            sty = Stylist(user_id=user.id, bio=bio, expertise=expertise, languages=languages, is_approved=True)
            db.session.add(sty)
            db.session.flush()
        if not StylistAvailability.query.filter_by(stylist_id=sty.id).first():
            base = datetime.utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
            for d in range(7):
                for hour in (5, 6, 9):  # 10:30, 11:30, 14:30 IST
                    start = base.replace(hour=hour, minute=0) + timedelta(days=d)
                    db.session.add(StylistAvailability(stylist_id=sty.id, start_at=start, end_at=start + timedelta(minutes=30)))
    db.session.commit()
    print("Seeded:", Product.query.count(), "products")
