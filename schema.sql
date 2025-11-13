-- schema.sql

-- Represents the B2B customer (the company using our SaaS)
CREATE TABLE Companies (
    company_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Warehouses belonging to a specific company
CREATE TABLE Warehouses (
    warehouse_id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES Companies(company_id),
    name VARCHAR(255) NOT NULL
);

-- The master product catalog, specific to a company
CREATE TABLE Products (
    product_id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES Companies(company_id),
    product_type_id INT REFERENCES ProductTypes(product_type_id),
    sku VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    price NUMERIC(10, 2) NOT NULL DEFAULT 0.00
);

-- Links Products and Warehouses
CREATE TABLE Inventory (
    inventory_id SERIAL PRIMARY KEY,
    product_id INT NOT NULL REFERENCES Products(product_id),
    warehouse_id INT NOT NULL REFERENCES Warehouses(warehouse_id),
    quantity INT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    UNIQUE(product_id, warehouse_id)
);

-- For business rules like "low stock threshold"
CREATE TABLE ProductTypes (
    product_type_id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES Companies(company_id),
    name VARCHAR(100) NOT NULL,
    low_stock_threshold INT NOT NULL DEFAULT 10
);

-- Suppliers who provide products
CREATE TABLE Suppliers (
    supplier_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    contact_email VARCHAR(255)
);

-- Links Products and Suppliers (Many-to-Many)
CREATE TABLE ProductSuppliers (
    product_id INT NOT NULL REFERENCES Products(product_id),
    supplier_id INT NOT NULL REFERENCES Suppliers(supplier_id),
    PRIMARY KEY (product_id, supplier_id)
);

-- Tables to track sales activity
CREATE TABLE SalesOrders (
    order_id SERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES Companies(company_id),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE SalesOrderItems (
    item_id SERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES SalesOrders(order_id),
    product_id INT NOT NULL REFERENCES Products(product_id),
    quantity INT NOT NULL,
    price_at_sale NUMERIC(10, 2) NOT NULL
);