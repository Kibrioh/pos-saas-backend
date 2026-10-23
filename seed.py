from decimal import Decimal

from sqlalchemy import text
import random
from faker import Faker

from app import create_app
from extensions import db
from models import (
    Tenant,
    Branch,
    User,
    Category,
    Product,
    Sale,
    SaleItem,
    StockMovement,
    Restock,
)

fake = Faker()
app = create_app()

with app.app_context():
    try:
        tenant = Tenant.query.order_by(Tenant.id.asc()).first()
        if tenant is None:
            tenant = Tenant(
                name="TechPoint Demo Business",
                slug="techpoint-demo-business",
            )
            db.session.add(tenant)
            db.session.flush()
        branch = Branch.query.filter_by(
            tenant_id=tenant.id,
            is_default=True,
        ).first()
        if branch is None:
            branch = Branch(
                tenant_id=tenant.id,
                name="Main Branch",
                is_default=True,
            )
            db.session.add(branch)
            db.session.flush()
        db.session.info["tenant_id"] = tenant.id
        db.session.info["branch_id"] = branch.id

        #This deletes all records in these tables.
        db.session.execute(
            text("""
                TRUNCATE TABLE
                    restocks,
                    stock_movements,
                    sale_items,
                    sales,
                    products,
                    categories,
                    suppliers,
                    users
                RESTART IDENTITY CASCADE
            """)
        )

        # --------------------------------------------------
        # 1. USERS
        # --------------------------------------------------
        manager = User(
            username="manager1",
            name="Moses Kariuki",
            role="manager",
        )
        manager.set_password("Manager123!")

        cashier1 = User(
            username="cashier1",
            name="Onyango Tate",
            role="cashier",
        )
        cashier2 = User(
            username="cashier2",
            name="Oscar Sudi",
            role="cashier",
        )
        cashier1.set_password("Cashier123!")
        cashier2.set_password("Cashier123!!")

        db.session.add_all([manager, cashier1, cashier2])
        db.session.flush()

        # --------------------------------------------------
        # 2. CATEGORIES
        # --------------------------------------------------
        category_names = [
            "Groceries",
            "Beverages",
            "Household",
            "Electronics",
            "Phones & Accessories",
            "Computers",
            "Fashion",
            "Shoes",
            "Beauty & Personal Care",
            "Home & Kitchen",
            "Sports & Outdoors",
            "Toys & Games",
            "Books & Stationery",
            "Automotive",
            "Baby Products",
        ]

        categories = {
            name: Category(name=name)
            for name in category_names
        }

        db.session.add_all(categories.values())
        db.session.flush()

        # --------------------------------------------------
        # 3. PRODUCTS
        # --------------------------------------------------
        catalog = {
            "Groceries": [
                ("Maize Flour 2kg", "Unga", 150, 220),
                ("Wheat Flour 2kg", "Exe", 170, 250),
                ("Sugar 1kg", "Kabras", 140, 190),
                ("Rice 2kg", "Pishori", 250, 450),
                ("Cooking Oil 1L", "Elianto", 250, 400),
                ("Beans 1kg", "Generic", 120, 220),
                ("Salt 1kg", "Kensalt", 40, 80),
                ("Peanut Butter 400g", "Blue Band", 180, 350),
            ],
            "Beverages": [
                ("Bottled Water 1L", "Keringet", 40, 80),
                ("Soda 500ml", "Coca-Cola", 50, 100),
                ("Orange Juice 1L", "Del Monte", 150, 300),
                ("Milk 500ml", "Brookside", 50, 90),
                ("Tea Leaves 250g", "Ketepa", 100, 220),
                ("Coffee 100g", "Nescafe", 180, 400),
            ],
            "Household": [
                ("Laundry Soap", "Menengai", 80, 160),
                ("Washing Powder 1kg", "Omo", 180, 350),
                ("Dishwashing Liquid 500ml", "Morning Fresh", 100, 220),
                ("Toilet Paper 10 Pack", "Velvex", 200, 400),
                ("Electric Kettle", "Ramtons", 1200, 3000),
                ("Steam Iron", "Philips", 2000, 6000),
            ],
            "Electronics": [
                ("Bluetooth Speaker", "JBL", 1500, 12000),
                ("Wireless Headphones", "Sony", 2000, 18000),
                ("Smart TV 43 inch", "Samsung", 25000, 55000),
                ("Power Bank 20000mAh", "Anker", 2000, 7000),
                ("USB Flash Drive 64GB", "SanDisk", 500, 1500),
                ("Wireless Mouse", "Logitech", 800, 3500),
                ("Wi-Fi Router", "TP-Link", 2000, 8000),
                ("Surge Protector", "Belkin", 1000, 4000),
            ],
            "Phones & Accessories": [
                ("Android Smartphone 128GB", "Samsung", 12000, 65000),
                ("iPhone 128GB", "Apple", 50000, 180000),
                ("USB-C Charger", "Anker", 800, 3000),
                ("Phone Case", "Generic", 200, 1500),
                ("Tempered Glass Screen Protector", "Generic", 100, 800),
                ("Wireless Earbuds", "Oraimo", 1500, 9000),
            ],
            "Computers": [
                ("Laptop 8GB RAM", "HP", 35000, 80000),
                ("Laptop 16GB RAM", "Lenovo", 55000, 150000),
                ("Gaming Laptop", "ASUS", 90000, 250000),
                ("Computer Monitor 24 inch", "Dell", 12000, 35000),
                ("Mechanical Keyboard", "Logitech", 2500, 12000),
                ("External SSD 1TB", "Samsung", 8000, 20000),
            ],
            "Fashion": [
                ("Men's Cotton T-Shirt", "Generic", 500, 2500),
                ("Women's Casual Dress", "Generic", 1200, 6000),
                ("Men's Denim Jeans", "Levi's", 2000, 8000),
                ("Women's Handbag", "Generic", 1000, 8000),
                ("Leather Belt", "Generic", 500, 2500),
                ("Sunglasses", "Ray-Ban", 1500, 15000),
            ],
            "Shoes": [
                ("Running Shoes", "Nike", 3500, 18000),
                ("Casual Sneakers", "Adidas", 2500, 15000),
                ("Leather Office Shoes", "Clarks", 3000, 12000),
                ("Women's Sandals", "Generic", 800, 5000),
                ("Hiking Boots", "Columbia", 5000, 20000),
            ],
            "Beauty & Personal Care": [
                ("Face Moisturizer", "Nivea", 500, 2500),
                ("Body Lotion 400ml", "Vaseline", 300, 1200),
                ("Shampoo 400ml", "Head & Shoulders", 400, 1500),
                ("Electric Hair Trimmer", "Philips", 1500, 7000),
                ("Perfume 100ml", "Calvin Klein", 2500, 12000),
                ("Sunscreen SPF 50", "Nivea", 800, 2500),
            ],
            "Home & Kitchen": [
                ("Non-stick Frying Pan", "Tefal", 1500, 6000),
                ("Dinner Plate Set", "Generic", 1000, 5000),
                ("Blender", "Ramtons", 2500, 9000),
                ("Microwave Oven", "Samsung", 9000, 25000),
                ("Bedsheet Set", "Generic", 1500, 6000),
                ("LED Desk Lamp", "Xiaomi", 1200, 5000),
            ],
            "Sports & Outdoors": [
                ("Football Size 5", "Adidas", 1000, 5000),
                ("Yoga Mat", "Generic", 800, 3500),
                ("Dumbbell Set", "Generic", 2000, 10000),
                ("Camping Tent 2 Person", "Coleman", 5000, 18000),
                ("Mountain Bicycle", "Generic", 18000, 60000),
            ],
            "Toys & Games": [
                ("Building Blocks Set", "LEGO", 1500, 12000),
                ("Remote Control Car", "Generic", 1200, 6000),
                ("Board Game", "Hasbro", 800, 4000),
                ("Plush Teddy Bear", "Generic", 500, 3000),
                ("Kids' Art Set", "Crayola", 500, 2500),
            ],
            "Books & Stationery": [
                ("A5 Notebook", "Generic", 100, 500),
                ("Ballpoint Pens 10 Pack", "BIC", 150, 600),
                ("School Backpack", "Generic", 1000, 5000),
                ("Desk Organizer", "Generic", 500, 2500),
                ("Wireless Printer", "HP", 8000, 25000),
            ],
            "Automotive": [
                ("Car Phone Holder", "Generic", 500, 2500),
                ("Portable Tyre Inflator", "Xiaomi", 2500, 8000),
                ("Car Vacuum Cleaner", "Generic", 1500, 6000),
                ("Dash Camera", "70mai", 4000, 18000),
                ("Jump Starter", "Anker", 5000, 20000),
            ],
            "Baby Products": [
                ("Baby Diapers Pack", "Pampers", 1000, 3500),
                ("Baby Wipes Pack", "Huggies", 150, 600),
                ("Baby Feeding Bottle", "Philips Avent", 500, 2500),
                ("Baby Stroller", "Generic", 8000, 30000),
                ("Baby Carrier", "Generic", 2000, 9000),
            ],
        }

        # --------------------------------------------------
        # GENERATE PRODUCTS
        # --------------------------------------------------

        TARGET_PRODUCT_COUNT = 10

        
        special_stock = {
            "Maize Flour 2kg": 10, 
            "Bottled Water 1L": 4,
            "Laundry Soap": 20,
        }

        product_specs = [
            (category_name, title, brand, low_price, high_price)
            for category_name, items in catalog.items()
            for title, brand, low_price, high_price in items
        ]

        # Every catalogue entry has a distinct title.
        # Add sensible variants if more rows are needed.
        variant_suffixes = [
            "Standard", "Premium", "Compact", "Deluxe",
            "Classic", "Plus", "XL", "Mini",
        ]

        
        # Keep the three products needed by the sample sale and restocking.
        required_titles = {
            "Non-stick Frying Pan",
            "Wireless Printer",
            "Microwave Oven",
            "Face Moisturizer",
            "Baby Stroller",
            "Perfume 100ml",
            "Bedsheet Set",
            "Maize Flour 2kg",
            "Bottled Water 1L",
            "Laundry Soap",
        }

        # Separate required products from the remaining catalogue.
        required_specs = [
            spec for spec in product_specs
            if spec[1] in required_titles
        ]

        other_specs = [
            spec for spec in product_specs
            if spec[1] not in required_titles
        ]

        if len(required_specs) != len(required_titles):
            raise ValueError(
                "One or more required products are missing from the catalogue."
            )

        # Select only enough other products to reach the target.
        random.shuffle(other_specs)

        remaining_slots = TARGET_PRODUCT_COUNT - len(required_specs)

        product_specs = required_specs + other_specs[:remaining_slots]

        # Generate variants only if the catalogue has fewer products than the target.
        existing_titles = {spec[1] for spec in product_specs}
        variant_suffixes = [
            "Standard", "Premium", "Compact", "Deluxe",
            "Classic", "Plus", "XL", "Mini",
        ]

        variant_specs = []

        while len(product_specs) + len(variant_specs) < TARGET_PRODUCT_COUNT:
            category_name, title, brand, low_price, high_price = random.choice(
                product_specs
            )

            suffix = random.choice(variant_suffixes)
            variant_title = f"{title} - {suffix}"

            if variant_title not in existing_titles:
                existing_titles.add(variant_title)
                variant_specs.append(
                    (category_name, variant_title, brand, low_price, high_price)
                )

        all_specs = (product_specs + variant_specs)[:TARGET_PRODUCT_COUNT]
        random.shuffle(all_specs)

        print(f"Products to create: {len(all_specs)}")

        PRODUCT_IMAGES = {
            "Non-stick Frying Pan": "https://shorturl.at/ysGk0",
            "Wireless Printer": "https://shorturl.at/pVdQK",
            "Microwave Oven": "https://shorturl.at/0A4le",
            "Face Moisturizer": "https://shorturl.at/xCjf2",
            "Baby Stroller": "https://shorturl.at/RWjyb",
            "Perfume 100ml": "https://tinyurl.com/mwp9kwhy",
            "Bedsheet Set": "https://tinyurl.com/2madrztk",
            "Maize Flour 2kg": "https://tinyurl.com/5jns8z3k",
            "Bottled Water 1L": "https://tinyurl.com/yr5hexh4",
            "Laundry Soap": "https://tinyurl.com/y4db26tb",
        }
        products = []

        for category_name, title, brand, low_price, high_price in all_specs:
            stock = special_stock.get(title, random.randint(0, 10))
            threshold = 5

            product = Product(
                title=title,
                brand=brand,
                price=Decimal(str(random.randint(low_price, high_price))),
                stock_quantity=stock,
                low_stock_threshold=threshold,
                category=categories[category_name],
                thumbnail=PRODUCT_IMAGES.get(
                        title,
                        "https://tinyurl.com/2e2ssvab"
                    ),
                description=fake.sentence(nb_words=12),
            )

            products.append(product)

        db.session.add_all(products)
        db.session.flush()

        
        # --------------------------------------------------
        # 4. INITIAL STOCK MOVEMENTS
        # --------------------------------------------------

        # Keep the generated Product objects in `products`.
        # Record initial stock for every generated product.
        for product in products:
            if product.stock_quantity > 0:
                db.session.add(
                    StockMovement(
                        product=product,
                        user=manager,
                        movement_type="initial_stock",
                        quantity_delta=product.stock_quantity,
                        stock_before=0,
                        stock_after=product.stock_quantity,
                        note="Initial stock created by development seed.",
                    )
                )

        # Retrieve specific products for the sample sale and restocks.
        flour = next(
            p for p in products
            if p.title == "Maize Flour 2kg"
        )

        water = next(
            p for p in products
            if p.title == "Bottled Water 1L"
        )

        soap = next(
            p for p in products
            if p.title == "Laundry Soap"
        )


        # --------------------------------------------------
        # 5. SAMPLE SALE AND SALE ITEMS
        # --------------------------------------------------
        sale_lines = [
            (flour, 2),
            (water, 3),
            (soap, 1),
        ]

        total_amount = Decimal("0.00")
        sale_details = []

        # Calculate totals and prepare stock deductions.
        for product, quantity in sale_lines:
            if quantity <= 0:
                raise ValueError(
                    f"Invalid quantity for {product.title}"
                )

            if product.stock_quantity < quantity:
                raise ValueError(
                    f"Insufficient stock for {product.title}"
                )

            stock_before = product.stock_quantity
            stock_after = stock_before - quantity
            subtotal = product.price * quantity

            total_amount += subtotal

            sale_details.append(
                (
                    product,
                    quantity,
                    stock_before,
                    stock_after,
                    subtotal,
                )
            )

            product.stock_quantity = stock_after

        sale = Sale(
            user=cashier1,
            total_amount=total_amount,
            payment_method="cash",
        )

        db.session.add(sale)
        db.session.flush()

        # --------------------------------------------------
        # 6. SALE ITEMS AND SALE STOCK MOVEMENTS
        # --------------------------------------------------
        for (
            product,
            quantity,
            stock_before,
            stock_after,
            subtotal,
        ) in sale_details:

            db.session.add(
                SaleItem(
                    sale=sale,
                    product=product,
                    quantity=quantity,
                    unit_price=product.price,
                    subtotal=subtotal,
                )
            )

            db.session.add(
                StockMovement(
                    product=product,
                    user=cashier1,
                    movement_type="sale",
                    quantity_delta=-quantity,
                    stock_before=stock_before,
                    stock_after=stock_after,
                    note=f"Stock deducted for seeded sale #{sale.id}.",
                )
            )
              
        # --------------------------------------------------
        # 6.5 SAMPLE RESTOCKS AND LINKED MOVEMENTS
        # --------------------------------------------------
        restock_specs = [
            {
                "product": flour,
                "quantity": 50,
                "unit_cost": Decimal("150.00"),
                "supplier": "Nairobi Wholesale Supplies",
                "invoice_number": "INV-2026-0042",
                "note": "Weekly restock",
            },
            {
                "product": water,
                "quantity": 100,
                "unit_cost": Decimal("40.00"),
                "supplier": "Coastal Beverages Ltd",
                "invoice_number": "INV-2026-0043",
                "note": "Bulk water order",
            },
            {
                "product": soap,
                "quantity": 30,
                "unit_cost": Decimal("80.00"),
                "supplier": "Nairobi Wholesale Supplies",
                "invoice_number": "INV-2026-0044",
                "note": None,
            },
        ]

        for spec in restock_specs:
            product = spec["product"]
            quantity = spec["quantity"]

            stock_before = product.stock_quantity
            stock_after = stock_before + quantity

            restock = Restock(
                product=product,
                user=manager,
                quantity=quantity,
                unit_cost=spec["unit_cost"],
                supplier=spec["supplier"],
                invoice_number=spec["invoice_number"],
                note=spec["note"],
            )
            db.session.add(restock)
            db.session.flush()

            product.stock_quantity = stock_after

            db.session.add(
                StockMovement(
                    product=product,
                    user=manager,
                    movement_type="restock",
                    quantity_delta=quantity,
                    stock_before=stock_before,
                    stock_after=stock_after,
                    restock_id=restock.id,
                    note=f"Linked to restock {spec['invoice_number']}",
                )
            )

        # --------------------------------------------------
        # 7. COMMIT ALL CHANGES
        # --------------------------------------------------
        db.session.commit()

        print("Database seeded successfully!")
        print(f"Users: {User.query.count()}")
        print(f"Categories: {Category.query.count()}")
        print(f"Products: {Product.query.count()}")
        print(f"Sales: {Sale.query.count()}")
        print(f"Sale items: {SaleItem.query.count()}")
        print(f"Stock movements: {StockMovement.query.count()}")
        print(f"Restocks: {Restock.query.count()}")
        print(f"Sample sale total: {total_amount}")

    except Exception:
        db.session.rollback()
        raise
