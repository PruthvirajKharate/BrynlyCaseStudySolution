# app.py
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, and_
from sqlalchemy.exc import IntegrityError

# --- App Setup ---
app = Flask(__name__)
# Use an in-memory SQLite database for this example
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# --- Model Definitions (Required for the app to run) ---
# We need to define the models based on our schema from Part 2
# so that SQLAlchemy can understand them.

class Company(db.Model):
    __tablename__ = 'Companies'
    company_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)

class Warehouse(db.Model):
    __tablename__ = 'Warehouses'
    warehouse_id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('Companies.company_id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)

class Product(db.Model):
    __tablename__ = 'Products'
    product_id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('Companies.company_id'), nullable=False)
    product_type_id = db.Column(db.Integer, db.ForeignKey('ProductTypes.product_type_id'))
    sku = db.Column(db.String(100), nullable=False, unique=True)
    name = db.Column(db.String(255), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)

class Inventory(db.Model):
    __tablename__ = 'Inventory'
    inventory_id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('Products.product_id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('Warehouses.warehouse_id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    __table_args__ = (db.UniqueConstraint('product_id', 'warehouse_id'),)

class ProductType(db.Model):
    __tablename__ = 'ProductTypes'
    product_type_id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('Companies.company_id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    low_stock_threshold = db.Column(db.Integer, nullable=False, default=10)

class Supplier(db.Model):
    __tablename__ = 'Suppliers'
    supplier_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    contact_email = db.Column(db.String(255))

class ProductSuppliers(db.Model):
    __tablename__ = 'ProductSuppliers'
    product_id = db.Column(db.Integer, db.ForeignKey('Products.product_id'), primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('Suppliers.supplier_id'), primary_key=True)

class SalesOrder(db.Model):
    __tablename__ = 'SalesOrders'
    order_id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('Companies.company_id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SalesOrderItems(db.Model):
    __tablename__ = 'SalesOrderItems'
    item_id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('SalesOrders.order_id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('Products.product_id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_at_sale = db.Column(db.Numeric(10, 2), nullable=False)


# --- API Endpoint 1 (Part 1 Solution) ---
@app.route('/api/products', methods=['POST'])
def create_product():
    """
    Creates a new product and its initial inventory record.
    Ensures the operation is atomic and all inputs are validated.
    """
    data = request.json
    
    # 1. Input Validation
    required_fields = ['name', 'sku', 'price', 'warehouse_id', 'initial_quantity']
    missing_fields = []
    for field in required_fields:
        if field not in data:
            missing_fields.append(field)
            
    if missing_fields:
        return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

    # 2. Sanitize & Type Cast Inputs
    try:
        product_name = str(data['name'])
        product_sku = str(data['sku'])
        product_price = Decimal(data['price'])
        warehouse_id = int(data['warehouse_id'])
        initial_quantity = int(data['initial_quantity'])

        if initial_quantity < 0:
            return jsonify({"error": "initial_quantity cannot be negative"}), 400
        
    except (InvalidOperation, ValueError, TypeError):
        return jsonify({"error": "Invalid data type for price, warehouse_id, or initial_quantity"}), 400

    # 3. Atomic Transaction Block
    try:
        product = Product(
            name=product_name,
            sku=product_sku,
            price=product_price
            # Note: company_id would also be needed in a real app
        )
        db.session.add(product)
        db.session.flush() 
        
        inventory = Inventory(
            product_id=product.product_id,
            warehouse_id=warehouse_id,
            quantity=initial_quantity
        )
        db.session.add(inventory)
        db.session.commit() 
        
        return jsonify({
            "message": "Product and initial inventory created successfully",
            "product_id": product.product_id
        }), 201

    except IntegrityError as e:
        db.session.rollback()
        if 'UNIQUE constraint failed: Products.sku' in str(e) or 'products_sku_key' in str(e):
            return jsonify({"error": f"Product with SKU '{product_sku}' already exists"}), 409
        return jsonify({"error": "Database integrity error"}), 500
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error creating product: {e}")
        return jsonify({"error": "An unexpected error occurred"}), 500


# --- API Endpoint 2 (Part 3 Solution) ---
@app.route('/api/companies/<int:company_id>/alerts/low-stock', methods=['GET'])
def get_low_stock_alerts(company_id):
    
    RECENT_DAYS = 30
    cutoff_date = datetime.utcnow() - timedelta(days=RECENT_DAYS)

    try:
        company = db.session.get(Company, company_id)
        if not company:
            return jsonify({"error": "Company not found"}), 404

        # Subquery: Find recently sold products
        recent_sales_subquery = db.session.query(
            SalesOrderItems.product_id,
            func.sum(SalesOrderItems.quantity).label('total_sold_recent')
        ).join(SalesOrder, SalesOrder.order_id == SalesOrderItems.order_id) \
         .filter(
            SalesOrder.company_id == company_id,
            SalesOrder.created_at >= cutoff_date
         ) \
         .group_by(SalesOrderItems.product_id) \
         .subquery()

        # Main query
        alerts_query = db.session.query(
            Product,
            Warehouse,
            Inventory,
            ProductType,
            recent_sales_subquery.c.total_sold_recent,
            Supplier 
        ) \
        .join(Warehouse, Inventory.warehouse_id == Warehouse.warehouse_id) \
        .join(Product, Inventory.product_id == Product.product_id) \
        .join(ProductType, Product.product_type_id == ProductType.product_type_id) \
        .join(recent_sales_subquery, Product.product_id == recent_sales_subquery.c.product_id) \
        .outerjoin(ProductSuppliers, Product.product_id == ProductSuppliers.product_id) \
        .outerjoin(Supplier, ProductSuppliers.supplier_id == Supplier.supplier_id) \
        .filter(
            Warehouse.company_id == company_id,
            Inventory.quantity <= ProductType.low_stock_threshold
        ) \
        .group_by(
            Product.product_id, 
            Warehouse.warehouse_id, 
            Inventory.inventory_id, 
            ProductType.product_type_id, 
            recent_sales_subquery.c.total_sold_recent, 
            Supplier.supplier_id
        )

        results = alerts_query.all()

        # Format response
        alerts = []
        for (product, warehouse, inventory, p_type, total_sold, supplier) in results:
            avg_daily_sale = total_sold / RECENT_DAYS
            days_until_stockout = None
            
            if avg_daily_sale > 0:
                days_until_stockout = int(inventory.quantity // avg_daily_sale)
            
            supplier_info = None
            if supplier:
                supplier_info = {
                    "id": supplier.supplier_id,
                    "name": supplier.name,
                    "contact_email": supplier.contact_email
                }

            alerts.append({
                "product_id": product.product_id,
                "product_name": product.name,
                "sku": product.sku,
                "warehouse_id": warehouse.warehouse_id,
                "warehouse_name": warehouse.name,
                "current_stock": inventory.quantity,
                "threshold": p_type.low_stock_threshold,
                "days_until_stockout": days_until_stockout,
                "supplier": supplier_info
            })
            
        return jsonify({
            "alerts": alerts,
            "total_alerts": len(alerts)
        })

    except Exception as e:
        logging.error(f"Error fetching low stock alerts for company {company_id}: {e}")
        return jsonify({"error": "An unexpected error occurred"}), 500


# --- Main entry point ---
if __name__ == '__main__':
    with app.app_context():
        # Create all the tables in the in-memory database
        db.create_all() 
    app.run(debug=True)