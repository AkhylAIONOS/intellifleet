# database.py

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from passlib.context import CryptContext
from backend.config.logger import logger
import json
from fastapi import HTTPException
from typing import List
from ..config.config import settings
import pandas as pd
from typing import Dict, Tuple
# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Database setup
DATABASE_URL = settings.DATABASE_URL

def init_db(db_path: str = "users.db"):
    """Create the canonical empty schema without replacing existing tables or rows."""
    with closing(sqlite3.connect(db_path)) as conn, conn:
        initialize_base_schema(conn)
    logger.info("Database initialized successfully")


def initialize_base_schema(conn: sqlite3.Connection) -> None:
    """Create base tables on the caller's connection before additive migrations."""
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL COLLATE NOCASE,
            password TEXT NOT NULL,
            verified BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Warehouses table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warehouses (
            warehouse_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            country TEXT NOT NULL,
            city TEXT NOT NULL,
            node_type TEXT NOT NULL,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                   
            PRIMARY KEY (user_id, warehouse_id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(user_id, name)
        )
    ''')
    
    # Vehicles table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            warehouse_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            label TEXT NOT NULL,
            capacity INTEGER DEFAULT 0,
            schedule_departure_time TIME,
            departure_time TIME,
            arrival_time TIME,
            current_location TEXT NOT NULL,
            is_available BOOLEAN DEFAULT 1,
            status TEXT DEFAULT 'available',
            current_position TEXT, 
            assigned_route TEXT,
            vehicle_details TEXT, 
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (user_id, warehouse_id) REFERENCES warehouses (user_id, warehouse_id)
        )
    ''')

    
    # Create routes table for persistent routes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS persistent_routes (
            route_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            parent_route_id INTEGER,
            route_data TEXT NOT NULL,
            waypoints TEXT NOT NULL, 
            source TEXT NOT NULL,
            destination TEXT NOT NULL,
            intermediate_locations TEXT,
            objective TEXT,
            is_active BOOLEAN DEFAULT 1,
            route_type TEXT NOT NULL DEFAULT 'road',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, route_id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (user_id, parent_route_id) REFERENCES persistent_routes (user_id, route_id)
        )
    ''')
    
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS nearest_airports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        warehouse_id INTEGER NOT NULL,
        warehouse_name TEXT NOT NULL,
        airport_name TEXT NOT NULL,
        airport_address TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        distance_km REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (user_id, warehouse_id) REFERENCES warehouses(user_id, warehouse_id),
        UNIQUE(user_id, warehouse_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warehouse_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        warehouse_id INTEGER NOT NULL,
        warehouse_name TEXT NOT NULL,
        inventory INTEGER DEFAULT 0,
        reorder_level INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (user_id, warehouse_id) REFERENCES warehouses(user_id, warehouse_id),
        UNIQUE(user_id, warehouse_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS multimodal_routes (
        route_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,

        multimodal_data TEXT NOT NULL,    
        segment_1 TEXT NOT NULL,          
        segment_2 TEXT NOT NULL,          
        segment_3 TEXT NOT NULL,          

        source TEXT NOT NULL,
        sourceNa TEXT NOT NULL,
        destinationNa TEXT NOT NULL,
        destination TEXT NOT NULL,
        objective TEXT,
        is_active BOOLEAN DEFAULT 1,
        route_type TEXT NOT NULL DEFAULT 'air',  
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,       
        PRIMARY KEY (user_id, route_id),
        FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
        user_id INTEGER NOT NULL,
        route_id INTEGER NOT NULL,
        from_location TEXT NOT NULL,
        to_location TEXT NOT NULL,
        distance REAL,
        duration REAL,
        cost REAL,
        route_type TEXT DEFAULT 'road',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nodes_air (
        user_id INTEGER NOT NULL,
        route_id INTEGER NOT NULL,
        from_location TEXT NOT NULL,
        to_location TEXT NOT NULL,
        distance REAL,
        duration REAL,
        cost REAL,
        route_type TEXT DEFAULT 'air',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nodes_combined (
        user_id INTEGER NOT NULL,
        route_id INTEGER NOT NULL,
        from_location TEXT NOT NULL,
        to_location TEXT NOT NULL,
        distance REAL,
        duration REAL,
        cost REAL,
        route_type TEXT CHECK(route_type IN ('road','air')) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

    # Create indexes for faster lookups
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_email ON users(email)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_warehouses_user ON warehouses(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vehicles_user ON vehicles(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vehicles_location ON vehicles(current_location)')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_nearest_airports_warehouse ON nearest_airports(warehouse_id)')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_persistent_routes_user ON persistent_routes(user_id)')

    # ------------------------------------------------------------------
    # ADDED: Missing indexes for routing performance
    # ------------------------------------------------------------------

    # nodes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_nodes_user ON nodes(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_nodes_from_location ON nodes(from_location)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_nodes_to_location ON nodes(to_location)')

    # nodes_air
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_nodes_air_user ON nodes_air(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_nodes_air_from_location ON nodes_air(from_location)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_nodes_air_to_location ON nodes_air(to_location)')

    # nodes_combined
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_nodes_combined_user ON nodes_combined(user_id)')

    # multimodal_routes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_multimodal_routes_user ON multimodal_routes(user_id)')


def get_db_connection():
    """Get SQLite database connection"""
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row 
    return conn


# ================================================================= AUTHENTICATION FUNCTIONS =================================================================
def get_user_by_email(email: str):
    """Get user by email from database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        return dict(user) if user else None
    except Exception as e:
        logger.error(f"Error getting user by email: {str(e)}")
        return None
    finally:
        conn.close()

def get_user_by_id(user_id: int):
    """Get user by ID from database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        return dict(user) if user else None
    except Exception as e:
        logger.error(f"Error getting user by ID: {str(e)}")
        return None
    finally:
        conn.close()

def create_user(user_data: dict):
    """Create new user in database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO users (first_name, last_name, email, password, verified, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_data['first_name'],
            user_data['last_name'],
            user_data['email'],
            user_data.get('password'),
            user_data.get('verified', False), 
            datetime.now(timezone.utc),
            datetime.now(timezone.utc)
        ))
        
        user_id = cursor.lastrowid
        conn.commit()
        
        # Get the created user
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        return dict(user) if user else None
        
    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed" in str(e):
            raise ValueError("Email already exists")
        raise e
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise e
    finally:
        conn.close()

def delete_user_data_warehouse(user_id: int):
    """
    Delete all data associated with a specific user_id from all tables.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Delete data from dependent tables first to avoid foreign key issues
        cursor.execute("DELETE FROM nearest_airports WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM persistent_routes WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM warehouses WHERE user_id = ?", (user_id,))
        cursor.execute('DELETE FROM warehouse_inventory WHERE user_id = ?', (user_id,))
        cursor.execute("DELETE FROM multimodal_routes WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM nodes WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM nodes_air WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM nodes_combined WHERE user_id = ?", (user_id,))

        # Commit changes
        conn.commit()
        logger.info(f"All warehouse data for user_id={user_id} has been deleted.")
    
    except Exception as e:
        logger.error(f"An error occurred while deleting user data: {e}")
        conn.rollback()
    
    finally:
        conn.close()

def delete_user_data_vehicle(user_id: int):
    """
    Delete all data associated with a specific user_id from all tables.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM vehicles WHERE user_id = ?", (user_id,))

        # Commit changes
        conn.commit()
        logger.info(f"All vehicle data for user_id={user_id} has been deleted.")
    
    except Exception as e:
        logger.error(f"An error occurred while deleting user data: {e}")
        conn.rollback()
    
    finally:
        conn.close()

# ============================================================== NEAREST AIRPORT FUNCTIONS =================================================================

def save_nearest_airport(user_id, warehouse_id, warehouse_name, airport):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Ensure valid clean values
        airport_name = str(airport.get("airport_name", ""))
        airport_address = str(airport.get("airport_address", ""))
        latitude = float(airport.get("latitude", 0.0))
        longitude = float(airport.get("longitude", 0.0))
        distance_km = airport.get("distance_km", None)

        cursor.execute("""
            INSERT OR REPLACE INTO nearest_airports 
            (user_id, warehouse_id, warehouse_name, airport_name, airport_address, latitude, longitude, distance_km)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            warehouse_id,
            warehouse_name,
            airport_name,
            airport_address,
            latitude,
            longitude,
            distance_km
        ))

        conn.commit()
        return cursor.lastrowid
    
    except Exception as e:
        logger.error(f"Error saving nearest_airport: {str(e)}")
        return None
    finally:
        conn.close()


def get_nearest_airport_by_city(city_name: str, user_id: int):

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT 
                w.name AS warehouse_name,
                na.airport_name,
                na.airport_address,
                na.latitude,
                na.longitude,
                na.distance_km
            FROM warehouses w
            JOIN nearest_airports na
                ON na.warehouse_id = w.warehouse_id
            AND na.user_id = w.user_id
            WHERE w.user_id = ?
            AND (
                    LOWER(w.name) LIKE LOWER(?)
                OR LOWER(w.address) LIKE LOWER(?)
            )
            LIMIT 1
        """, (user_id, f"%{city_name}%", f"%{city_name}%"))

        row = cursor.fetchone()
        if not row:
            return None
        
        return {
            "warehouse_name": row["warehouse_name"],
            "airport_name": row["airport_name"],
            "airport_address": row["airport_address"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "distance_km": row["distance_km"]
        }
    except Exception as e:
        logger.error(f"Error getting nearest airport by city {city_name}: {str(e)}")
        return None
    finally:
        conn.close()


# ================================================================ WAREHOUSE MANAGEMENT FUNCTIONS ================================================================

def get_next_warehouse_id(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT COALESCE(MAX(warehouse_id), 0) + 1
            FROM warehouses
            WHERE user_id = ?
        """, (user_id,))
        wid = cursor.fetchone()[0]
        return wid

    except Exception as e:
        logger.error(f"Error generating ID: {str(e)}")
        return None
    finally:
        conn.close()

def create_warehouse(user_id: int, warehouse_data: dict):
    """Create new warehouse in database"""

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        warehouse_id = get_next_warehouse_id(user_id)

        # Insert warehouse info
        cursor.execute('''
            INSERT INTO warehouses (user_id, warehouse_id, country, city, node_type, name, address, latitude, longitude, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            warehouse_id,
            warehouse_data['country'],
            warehouse_data['city'],
            warehouse_data['node_type'],
            warehouse_data['name'],
            warehouse_data['address'],
            warehouse_data.get('latitude'),
            warehouse_data.get('longitude'),
            warehouse_data.get('is_active', True),
            datetime.now(timezone.utc),
            datetime.now(timezone.utc)
        ))
        
        inventory_value = warehouse_data.get('inventory') or warehouse_data.get('inventory/capacity', 0)
        reorder_level_value = warehouse_data.get('reorder_level') or warehouse_data.get('reorderlevel', 0)

        # Insert inventory info
        cursor.execute('''
            INSERT INTO warehouse_inventory (user_id, warehouse_id, warehouse_name, inventory, reorder_level, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            warehouse_id,
            warehouse_data["name"],
            inventory_value,
            reorder_level_value,
            datetime.now(timezone.utc),
            datetime.now(timezone.utc)
        ))
        
        conn.commit()
        return warehouse_id
        
    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed" in str(e):
            raise ValueError("Warehouse name already exists for this user")
        raise e
    except Exception as e:
        logger.error(f"Error creating warehouse: {str(e)}")
        raise e
    finally:
        conn.close()


def get_warehouses_by_user(user_id: int):
    """Get all warehouses for a user WITH nearest airport"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT 
                w.*,
                wi.inventory, wi.reorder_level,
                na.airport_name, na.airport_address, na.latitude AS airport_latitude, na.longitude AS airport_longitude, na.distance_km
            FROM warehouses w
            LEFT JOIN warehouse_inventory wi
                ON w.warehouse_id = wi.warehouse_id AND w.user_id = wi.user_id
            LEFT JOIN nearest_airports na
                ON w.warehouse_id = na.warehouse_id AND w.user_id = na.user_id
            WHERE w.user_id = ? AND w.is_active = 1
            ORDER BY w.name
        ''', (user_id,))

        
        warehouses = []
        for row in cursor.fetchall():
            warehouse = dict(row)

            warehouse['inventory'] = warehouse.pop('inventory', 0)
            warehouse['reorder_level'] = warehouse.pop('reorder_level', 0)

            # ✅ Attach nearest airport properly
            if warehouse.get("airport_name"):
                warehouse["nearest_airport"] = {
                    "airport_name": warehouse.pop("airport_name"),
                    "airport_address": warehouse.pop("airport_address"),
                    "latitude": warehouse.pop("airport_latitude"),
                    "longitude": warehouse.pop("airport_longitude"),
                    "distance_km": warehouse.pop("distance_km"),
                }
            else:
                warehouse["nearest_airport"] = None
                warehouse.pop("airport_name", None)
                warehouse.pop("airport_address", None)
                warehouse.pop("airport_latitude", None)
                warehouse.pop("airport_longitude", None)
                warehouse.pop("distance_km", None)

            warehouses.append(warehouse)
        
        return warehouses

    except Exception as e:
        logger.error(f"Error getting warehouses: {str(e)}")
        return []
    finally:
        conn.close()


def get_warehouses_by_userall(user_id: int):
    """Get all warehouses for a user WITH nearest airport"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT 
                w.*,
                wi.inventory, wi.reorder_level,
                na.airport_name, na.airport_address, na.latitude AS airport_latitude, na.longitude AS airport_longitude, na.distance_km
            FROM warehouses w
            LEFT JOIN warehouse_inventory wi
                ON w.warehouse_id = wi.warehouse_id AND w.user_id = wi.user_id
            LEFT JOIN nearest_airports na
                ON w.warehouse_id = na.warehouse_id AND w.user_id = na.user_id
            WHERE w.user_id = ?
            ORDER BY w.name
        ''', (user_id,))

        
        warehouses = []
        for row in cursor.fetchall():
            warehouse = dict(row)

            warehouse['inventory'] = warehouse.pop('inventory', 0)
            warehouse['reorder_level'] = warehouse.pop('reorder_level', 0)

            # ✅ Attach nearest airport properly
            if warehouse.get("airport_name"):
                warehouse["nearest_airport"] = {
                    "airport_name": warehouse.pop("airport_name"),
                    "airport_address": warehouse.pop("airport_address"),
                    "latitude": warehouse.pop("airport_latitude"),
                    "longitude": warehouse.pop("airport_longitude"),
                    "distance_km": warehouse.pop("distance_km"),
                }
            else:
                warehouse["nearest_airport"] = None
                warehouse.pop("airport_name", None)
                warehouse.pop("airport_address", None)
                warehouse.pop("airport_latitude", None)
                warehouse.pop("airport_longitude", None)
                warehouse.pop("distance_km", None)

            warehouses.append(warehouse)
        
        return warehouses

    except Exception as e:
        logger.error(f"Error getting warehouses: {str(e)}")
        return []
    finally:
        conn.close()


def get_warehouse_by_name(user_id: int, name: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT
                w.*,
                SUM(CASE WHEN v.type = 'truck' THEN 1 ELSE 0 END) AS trucks,
                SUM(CASE WHEN v.type = 'car' THEN 1 ELSE 0 END) AS cars,
                SUM(CASE WHEN v.type = 'bike' THEN 1 ELSE 0 END) AS bikes,
                SUM(CASE WHEN v.type = 'auto' THEN 1 ELSE 0 END) AS autos,
                na.airport_name,
                na.airport_address,
                na.latitude AS airport_latitude,
                na.longitude AS airport_longitude,
                na.distance_km
            FROM warehouses w
            LEFT JOIN vehicles v
                ON w.warehouse_id = v.warehouse_id
               AND w.user_id = v.user_id
            LEFT JOIN nearest_airports na
                ON w.warehouse_id = na.warehouse_id
               AND w.user_id = na.user_id
            WHERE w.user_id = ? AND LOWER(w.name) = LOWER(?)
            GROUP BY w.warehouse_id, w.user_id
        ''', (user_id, name))
        
        row = cursor.fetchone()
        if not row:
            return None

        warehouse = dict(row)

        warehouse['vehicles'] = {
            'trucks': warehouse.pop('trucks', 0),
            'cars': warehouse.pop('cars', 0),
            'bikes': warehouse.pop('bikes', 0),
            'autos': warehouse.pop('autos', 0)
        }

        if warehouse.get("airport_name"):
            warehouse["nearest_airport"] = {
                "airport_name": warehouse.pop("airport_name"),
                "airport_address": warehouse.pop("airport_address"),
                "latitude": warehouse.pop("airport_latitude"),
                "longitude": warehouse.pop("airport_longitude"),
                "distance_km": warehouse.pop("distance_km"),
            }
        else:
            warehouse["nearest_airport"] = None
            warehouse.pop("airport_name", None)
            warehouse.pop("airport_address", None)
            warehouse.pop("airport_latitude", None)
            warehouse.pop("airport_longitude", None)
            warehouse.pop("distance_km", None)

        return warehouse

    except Exception as e:
        logger.error(f"Error getting warehouse by name: {str(e)}")
        return None
    finally:
        conn.close()


def delete_warehouse(user_id: int, warehouse_id: int):
    """Soft delete a single warehouse"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE warehouses
            SET is_active = 0,
                updated_at = ?
            WHERE user_id = ? AND warehouse_id = ?
        ''', (
            datetime.now(timezone.utc),
            user_id,
            warehouse_id
        ))

        conn.commit()
        logger.info(
            f"Soft-deleted warehouse {warehouse_id} for user {user_id}"
        )
    
    except Exception as e:
        logger.error(f"Error deleting warehouse {warehouse_id}: {str(e)}")
        return None
    finally:
        conn.close()

def reactivate_warehouse(user_id: int, warehouse_id: int):
    """Reactivate a soft-deleted warehouse"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE warehouses
            SET is_active = 1,
                updated_at = ?
            WHERE user_id = ? AND warehouse_id = ?
        ''', (
            datetime.now(timezone.utc),
            user_id,
            warehouse_id
        ))

        conn.commit()
        logger.info(
            f"Reactivated warehouse {warehouse_id} for user {user_id}"
        )
    
    except Exception as e:
        logger.error(f"Error reactivating warehouse {warehouse_id}: {str(e)}")
        return None

    finally:
        conn.close()

# =============================================================== VEHICLE MANAGEMENT FUNCTIONS ===============================================================

def create_vehicle(user_id: int, vehicle_data: dict):
    """Create new vehicle in database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        current_position = json.dumps(vehicle_data.get('current_position', {})) if vehicle_data.get('current_position') else None
        assigned_route = json.dumps(vehicle_data.get('assigned_route', {})) if vehicle_data.get('assigned_route') else None
        vehicle_details = json.dumps(vehicle_data.get('vehicle_details', {})) if vehicle_data.get('vehicle_details') else None
        cursor.execute('''
            INSERT INTO vehicles (user_id, warehouse_id, type, label, current_location, is_available, capacity, schedule_departure_time, departure_time, arrival_time,
                                status, current_position, assigned_route, vehicle_details, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            vehicle_data['warehouse_id'],
            vehicle_data['type'],
            vehicle_data['label'],
            vehicle_data['current_location'],
            vehicle_data.get('is_available', True),
            vehicle_data.get("capacity", 0),
            vehicle_data.get('schedule_departure_time'),
            vehicle_data.get("departure_time"),
            vehicle_data.get('arrival_time'),
            vehicle_data.get('status', 'available'),
            current_position,
            assigned_route,
            vehicle_details,
            vehicle_data.get('is_active', True),
            datetime.now(timezone.utc),
            datetime.now(timezone.utc)
        ))
        
        vehicle_id = cursor.lastrowid
        conn.commit()
        return vehicle_id
        
    except Exception as e:
        logger.error(f"Error creating vehicle: {str(e)}")
        raise e
    finally:
        conn.close()

def get_vehicles_by_user(user_id: int):
    """Get all vehicles for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT v.*, w.name as warehouse_name
            FROM vehicles v
            LEFT JOIN warehouses w ON v.warehouse_id = w.warehouse_id AND v.user_id = w.user_id
            WHERE v.user_id = ?
            ORDER BY v.type, v.label
        ''', (user_id,))
        
        vehicles = []
        for row in cursor.fetchall():
            vehicle = dict(row)
            # Parse JSON fields
            if vehicle.get('current_position'):
                vehicle['current_position'] = json.loads(vehicle['current_position'])
            if vehicle.get('assigned_route'):
                vehicle['assigned_route'] = json.loads(vehicle['assigned_route'])
            if vehicle.get('vehicle_details'):
                vehicle['vehicle_details'] = json.loads(vehicle['vehicle_details'])
            vehicles.append(vehicle)
        
        return vehicles
    except Exception as e:
        logger.error(f"Error getting vehicles: {str(e)}")
        return []
    finally:
        conn.close()


def get_available_vehicles_at_location(user_id: int, location_name: str, vehicle_type: str = None):
    """Get available vehicles at specific location for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        query = '''
            SELECT v.*, w.name as warehouse_name
            FROM vehicles v
            LEFT JOIN warehouses w 
                ON v.warehouse_id = w.warehouse_id 
            AND v.user_id = w.user_id
            WHERE v.user_id = ? 
            AND w.name = ? 
            AND v.is_available = 1
            AND v.is_active = 1
        '''

        params = [user_id, location_name]
        
        if vehicle_type:
            query += ' AND v.type = ?'
            params.append(vehicle_type)
            
        query += ' ORDER BY v.type, v.label'
        
        cursor.execute(query, params)
        
        vehicles = []
        for row in cursor.fetchall():
            vehicle = dict(row)
            # Parse JSON fields
            if vehicle.get('current_position'):
                vehicle['current_position'] = json.loads(vehicle['current_position'])
            if vehicle.get('assigned_route'):
                vehicle['assigned_route'] = json.loads(vehicle['assigned_route'])
            vehicles.append(vehicle)
        
        return vehicles
    except Exception as e:
        logger.error(f"Error getting available vehicles: {str(e)}")
        return []
    finally:
        conn.close()

# def update_vehicle(vehicle_id: int, user_id: int, update_data: dict):
#     """Update vehicle information"""
#     conn = get_db_connection()
#     cursor = conn.cursor()
    
#     try:
#         set_clauses = []
#         params = []
        
#         for key, value in update_data.items():
#             if key == 'current_position' and value is not None:
#                 set_clauses.append('current_position = ?')
#                 params.append(json.dumps(value))
#             elif key == 'assigned_route' and value is not None:
#                 set_clauses.append('assigned_route = ?')
#                 params.append(json.dumps(value))
#             elif key == 'vehicle_details' and value is not None:
#                 set_clauses.append('vehicle_details = ?')
#                 params.append(json.dumps(value))
#             elif key == 'departure_time' and value is not None:
#                 set_clauses.append('departure_time = ?')
#                 params.append(value)
#             elif key == 'arrival_time' and value is not None:
#                 set_clauses.append('arrival_time = ?')
#                 params.append(value)
#             else:
#                 set_clauses.append(f'{key} = ?')
#                 params.append(value)
        
#         set_clauses.append('updated_at = ?')
#         params.append(datetime.now(timezone.utc))
        
#         params.extend([vehicle_id, user_id])
        
#         query = f'UPDATE vehicles SET {", ".join(set_clauses)} WHERE id = ? AND user_id = ?'
#         cursor.execute(query, params)
        
#         conn.commit()
#         return cursor.rowcount > 0
        
#     except Exception as e:
#         logger.error(f"Error updating vehicle: {str(e)}")
#         return False
#     finally:
#         conn.close()

def update_vehicle(vehicle_id: int, user_id: int, update_data: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        set_clauses = []
        params = []
        
        for key, value in update_data.items():
            
            if key == 'current_position':
                set_clauses.append('current_position = ?')
                params.append(json.dumps(value) if value is not None else None)

            elif key == 'assigned_route':
                set_clauses.append('assigned_route = ?')
                params.append(json.dumps(value) if value is not None else None)

            elif key == 'vehicle_details':
                set_clauses.append('vehicle_details = ?')
                params.append(json.dumps(value) if value is not None else None)

            elif key in ['departure_time', 'arrival_time']:
                set_clauses.append(f'{key} = ?')
                params.append(value)

            else:
                set_clauses.append(f'{key} = ?')
                params.append(value)

        set_clauses.append('updated_at = ?')
        params.append(datetime.now(timezone.utc).isoformat())

        params.extend([int(vehicle_id), int(user_id)])

        query = f'UPDATE vehicles SET {", ".join(set_clauses)} WHERE id = ? AND user_id = ?'
        
        # logger.info(f"[QUERY] {query}")
        # logger.info(f"[PARAMS] {params}")

        cursor.execute(query, params)
        rows_affected = cursor.rowcount
        conn.commit()

        # logger.info(f"[ROWCOUNT] {rows_affected}")

        return rows_affected > 0
        
    except Exception as e:
        logger.error(f"Error updating vehicle: {str(e)}", exc_info=True)
        return False

    finally:
        conn.close()

def delete_user_vehicles(user_id: int):
    """Delete all vehicles for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('DELETE FROM vehicles WHERE user_id = ?', (user_id,))
        conn.commit()
        logger.info(f"Deleted all vehicles for user {user_id}")
    except Exception as e:
        logger.error(f"Error deleting user vehicles: {str(e)}")
        raise e
    finally:
        conn.close()


def get_available_vehicles_with_capacity(user_id: int, location_name: str, capacity: int, vehicle_type: str = None):
    """Get available vehicles at specific location for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        query = '''
            SELECT v.*, w.name as warehouse_name
            FROM vehicles v
            LEFT JOIN warehouses w 
                ON v.warehouse_id = w.warehouse_id 
            AND v.user_id = w.user_id
            WHERE v.user_id = ? 
            AND w.name = ? 
            AND v.is_available = 1
            AND v.is_active = 1
        '''

        params = [user_id, location_name]
        
        if capacity:
            query += ' AND v.capacity = ?'
            params.append(capacity)
            
        if vehicle_type:
            query += ' AND v.type = ?'
            params.append(vehicle_type)


        query += ' ORDER BY v.type, v.label'
        
        cursor.execute(query, params)
        
        vehicles = []
        for row in cursor.fetchall():
            vehicle = dict(row)
            # Parse JSON fields
            if vehicle.get('current_position'):
                vehicle['current_position'] = json.loads(vehicle['current_position'])
            if vehicle.get('assigned_route'):
                vehicle['assigned_route'] = json.loads(vehicle['assigned_route'])
            vehicles.append(vehicle)
        
        return vehicles
    except Exception as e:
        logger.error(f"Error getting available vehicles: {str(e)}")
        return []
    finally:
        conn.close()

def deactivate_vehicle(user_id: int, vehicle_id: int):
    """Soft delete a single warehouse"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE vehicles
            SET is_active = 0,
                updated_at = ?
            WHERE user_id = ? AND id = ?
        ''', (
            datetime.now(timezone.utc),
            user_id,
            vehicle_id
        ))

        conn.commit()
        logger.info(
            f"Deactivated vehicle {vehicle_id} for user {user_id}"
        )
    
    except Exception as e:
        logger.error(f"Error deactivating vehicle {vehicle_id}: {str(e)}")
        return None
    finally:
        conn.close()

def reactivate_vehicle(user_id: int, vehicle_id: int):
    """Reactivate a soft-deleted vehicle"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE vehicles
            SET is_active = 1,
                updated_at = ?
            WHERE user_id = ? AND id = ?
        ''', (
            datetime.now(timezone.utc),
            user_id,
            vehicle_id
        ))

        conn.commit()
        logger.info(
            f"Reactivated vehicle {vehicle_id} for user {user_id}"
        )
    
    except Exception as e:
        logger.error(f"Error reactivating vehicle {vehicle_id}: {str(e)}")
        return None

    finally:
        conn.close()

def get_vehicle_by_id(vehicle_id: int, user_id: int):
    """Fetch a single vehicle by ID (only active vehicles)"""
    conn = get_db_connection()  
    cursor = conn.cursor()

    try:
        cursor.execute('''
            SELECT *
            FROM vehicles
            WHERE id = ? AND user_id = ?
            LIMIT 1
        ''', (vehicle_id, user_id,))

        row = cursor.fetchone()
        if not row:
            return None

        # Convert row to dict
        columns = [col[0] for col in cursor.description]
        vehicle = dict(zip(columns, row))
        logger.info(f"Fetched vehicle {vehicle_id}")
        return vehicle

    except sqlite3.Error as e:
        logger.error(f"Error fetching vehicle {vehicle_id}: {str(e)}")
        return None

    finally:
        conn.close()

# =============================================================== PERSISTENT ROUTE FUNCTIONS ===============================================================

def get_next_route_id(user_id):

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT COALESCE(MAX(route_id), 0) + 1
            FROM (
                SELECT route_id FROM persistent_routes WHERE user_id = ?
                UNION ALL
                SELECT route_id FROM multimodal_routes WHERE user_id = ?
            )
        """, (user_id, user_id))
        rid = cursor.fetchone()[0]
        return rid
    
    except Exception as e:
        logger.error(f"Error generating ID: {str(e)}")
        return None
    finally:
        conn.close()


def save_persistent_route(user_id: int, route_data: dict, parent_route_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    route_id = get_next_route_id(user_id)

    try:
        route_data_json = json.dumps(route_data)
        waypoints_json = json.dumps(route_data.get("locations", []))

        cursor.execute("""
            INSERT INTO persistent_routes 
            (route_id, user_id, parent_route_id, route_data, waypoints, source, destination, intermediate_locations, objective, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            route_id,
            user_id,
            parent_route_id,
            route_data_json,
            waypoints_json,
            route_data["source"],
            route_data["destination"],
            json.dumps(route_data.get("intermediate_locations", [])),
            route_data.get("objective", ""),
            datetime.now(timezone.utc)
        ))


        conn.commit()

        return route_id

    except Exception as e:
        logger.error(f"Error saving persistent route: {str(e)}")
        raise HTTPException(500, "Failed to save route")
    finally:
        conn.close()


def get_persistent_route_by_id(user_id: int, route_id: int):
    
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            SELECT * FROM persistent_routes 
            WHERE route_id = ? AND user_id = ? AND is_active = 1
        ''', (route_id, user_id))

        row = cursor.fetchone()
        if not row:
            return None

        route = dict(row)

        # Decode JSON fields
        route['route_data'] = json.loads(route['route_data']) if route.get('route_data') else None
        route['waypoints'] = json.loads(route['waypoints']) if route.get('waypoints') else []

        return route

    except Exception as e:
        logger.error(f"Error getting persistent route by id {route_id}: {str(e)}")
        return None
    finally:
        conn.close()
        

def delete_persistent_route(user_id: int, route_id: int):
   
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            DELETE FROM persistent_routes
            WHERE route_id = ? AND user_id = ?
        """, (route_id, user_id))
        
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted

    except Exception as e:
        logger.error(f"Error deleting persistent route: {str(e)}")
        return False

    finally:
        cursor.close()
        conn.close()


def get_persistent_route_by_locations(
    user_id: int,
    source: str,
    destination: str,
    intermediate_locations: list = None,
    objective: str = None
):
    """
    Retrieve a persistent route for the given user and route parameters.
    Source, destination, and objective are compared case‑insensitively.
    Intermediate locations are compared case‑insensitively in Python.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # First, fetch all active routes for the user with matching source/destination (case‑insensitive)
        # and matching objective (if provided). We'll later filter intermediate_locations in Python.
        sql = """
            SELECT * FROM persistent_routes
            WHERE user_id = ?
            AND LOWER(source) = LOWER(?)
            AND LOWER(destination) = LOWER(?)
            AND is_active = 1
        """
        params = [user_id, source, destination]

        # Objective filter (case‑insensitive)
        if objective is not None:
            sql += " AND LOWER(objective) = LOWER(?)"
            params.append(objective)
        else:
            sql += " AND (objective IS NULL OR objective = '')"

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        if not rows:
            return None

        # Convert rows to dicts
        routes = [dict(row) for row in rows]

        # If intermediate_locations is provided, filter those routes where the stored intermediate locations
        # match case‑insensitively. The stored value may be JSON string, NULL, or empty array.
        if intermediate_locations is not None:
            # Normalize user-provided list to lowercase for comparison
            norm_user_intermediate = [loc.lower() for loc in intermediate_locations]

            def match_intermediate(route):
                stored = route.get("intermediate_locations")
                if stored is None:
                    stored_list = []
                else:
                    # stored is a JSON string; parse it
                    if isinstance(stored, str):
                        stored_list = json.loads(stored)
                    else:
                        stored_list = stored  # fallback
                # Normalize stored list to lowercase
                norm_stored = [loc.lower() for loc in stored_list]
                return norm_stored == norm_user_intermediate

            # Filter routes
            routes = [r for r in routes if match_intermediate(r)]
        else:
            # No intermediate filter: only keep routes that have NULL or empty intermediate_locations
            routes = [r for r in routes if not r.get("intermediate_locations") or r["intermediate_locations"] == "[]"]

        if not routes:
            return None

        # Return the first match (oldest? could add ORDER BY if needed)
        return routes[0]

    except Exception as e:
        logger.error(f"Error getting persistent route by locations: {str(e)}")
        return None
    finally:
        conn.close()

# def get_persistent_route_by_locations(
#     user_id: int,
#     source: str,
#     destination: str,
#     intermediate_locations: list = None,
#     objective: str = None
# ):
#     conn = get_db_connection()
#     cursor = conn.cursor()

#     try:
#         sql = """
#             SELECT * FROM persistent_routes
#             WHERE user_id = ?
#             LOWER(source) = LOWER(?)     
#             AND LOWER(destination) = LOWER(?) 
#             AND is_active = 1
#         """

#         params = [user_id, source, destination]

#         # ---- Intermediate locations filter ----
#         if intermediate_locations is not None:
#             intermediate_json = json.dumps(intermediate_locations)
#             sql += " AND intermediate_locations = ?"
#             params.append(intermediate_json)
#         else:
#             sql += " AND (intermediate_locations IS NULL OR intermediate_locations = '[]')"

#         # ---- Objective filter (NEW) ----
#         if objective is not None:
#             sql += " AND LOWER(objective) = ?"              # <-- NEW
#             params.append(objective.lower())
#         else:
#             sql += " AND (objective IS NULL OR objective = '')"  # <-- NEW

#         sql += " LIMIT 1"

#         cursor.execute(sql, params)
#         row = cursor.fetchone()

#         return dict(row) if row else None

#     except Exception as e:
#         logger.error(f"Error getting persistent route by locations: {str(e)}")
#         return None
#     finally:
#         conn.close()


def get_persistent_route_by_waypoints(user_id: int, waypoints: List[str]):
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM persistent_routes
            WHERE user_id = ? AND waypoints = ?
            LIMIT 1
        """, (user_id, json.dumps(waypoints)))
        row = cursor.fetchone()
        if row:
            route = dict(row)
            route['route_data'] = json.loads(route['route_data'])
            route['waypoints'] = json.loads(route['waypoints'])
            return route
    except Exception as e:
        logger.error(f"Error getting persistent route by waypoints: {str(e)}")
    finally:
        conn.close()

def deactivate_route(route_id: int, user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE persistent_routes
            SET is_active = 0
            WHERE route_id = ? AND user_id = ?
        """, (route_id, user_id,))

        conn.commit()
    
    except Exception as e:
        logger.error(f"Error deactivating route by id {route_id}: {str(e)}")
        return None
    finally:
        conn.close()


def fetch_warehouse_inventory_summary(user_id: int) -> List[dict]:
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        query = """
            SELECT warehouse_id, warehouse_name, inventory, reorder_level
            FROM warehouse_inventory
            WHERE user_id = ?
        """

        cursor.execute(query, (user_id,))
        rows = cursor.fetchall()

        return [dict(row) for row in rows]
    
    except Exception as e:
        logger.error(f"Error fetching inventory: {str(e)}")
        return None
    finally:
        conn.close()



#=================================================================== Multimodal ========================================================================================

def save_multimodal_route(user_id: int, multimodal_data: dict):
    conn = get_db_connection()
    cursor = conn.cursor()

    multimodal_route_id = get_next_route_id(user_id)

    try:
        cursor.execute("""
            INSERT INTO multimodal_routes 
            (
                route_id,
                user_id,
                multimodal_data,
                segment_1,
                segment_2,
                segment_3,
                source,
                sourceNa,
                destinationNa,
                destination,
                objective,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            multimodal_route_id,
            user_id,

            json.dumps(multimodal_data),
            json.dumps(multimodal_data.get("segment_1", {})),
            json.dumps(multimodal_data.get("segment_2", {})),
            json.dumps(multimodal_data.get("segment_3", {})),

            multimodal_data["segment_1"]["source"],                
            multimodal_data["segment_2"]["source_airport_name"],   
            multimodal_data["segment_2"]["destination_airport_name"], 
            multimodal_data["segment_3"]["destination"],           
            multimodal_data.get("objective", ""),
            datetime.now(timezone.utc)
        ))

        conn.commit()
        return multimodal_route_id

    except Exception as e:
        logger.error(f"Error saving multimodal route: {str(e)}")
        raise HTTPException(500, "Failed to save multimodal route")

    finally:
        conn.close()


def get_multimodal_route_by_id(user_id: int, multimodal_route_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            SELECT * FROM multimodal_routes
            WHERE route_id = ? 
              AND user_id = ?
              AND is_active = 1
        ''', (multimodal_route_id, user_id))

        row = cursor.fetchone()
        if not row:
            return None

        route = dict(row)

        route['multimodal_data'] = json.loads(route['multimodal_data'])
        route['segment_1'] = json.loads(route['segment_1'])
        route['segment_2'] = json.loads(route['segment_2'])
        route['segment_3'] = json.loads(route['segment_3'])

        return route

    except Exception as e:
        logger.error(f"Error getting multimodal route by id {multimodal_route_id}: {str(e)}")
        return None

    finally:
        conn.close()


def delete_multimodal_route(user_id: int, multimodal_route_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            DELETE FROM multimodal_routes
            WHERE route_id = ? AND user_id = ?
        """, (multimodal_route_id, user_id))

        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted

    except Exception as e:
        logger.error(f"Error deleting multimodal route: {str(e)}")
        return False

    finally:
        cursor.close()
        conn.close()

# def get_multimodal_route_by_source_dest(user_id, source, destination, objective):
#     conn = get_db_connection()
#     cursor = conn.cursor()

#     try:
#         cursor.execute("""
#             SELECT * FROM multimodal_routes
#             WHERE user_id = ?
#             AND source = ?
#             AND destination = ?
#             AND is_active = 1
#             LIMIT 1
#         """, (user_id, source, destination))

#         row = cursor.fetchone()

#         return dict(row) if row else None
    
#     except Exception as e:
#         logger.error(f"Error getting multimodal route: {str(e)}")
#         return None
#     finally:
#         conn.close()


def get_multimodal_route_by_source_dest(user_id, source, destination, objective=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Base query
        query = """
            SELECT * FROM multimodal_routes
            WHERE user_id = ?
            AND LOWER(source) = LOWER(?)
            AND LOWER(destination) = LOWER(?)
            AND is_active = 1
        """

        params = [user_id, source, destination]

        # Add objective condition only if objective is provided
        if objective is not None:
            query += " AND LOWER(objective) = ?"              # <-- NEW
            params.append(objective)
        else:
            query += " AND (objective IS NULL OR objective = '')"  # <-- NEW

        query += " LIMIT 1"

        cursor.execute(query, params)

        row = cursor.fetchone()
        return dict(row) if row else None

    except Exception as e:
        logger.error(f"Error getting multimodal route: {str(e)}")
        return None
    finally:
        conn.close()


def get_hub_and_capitals(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT name, city, node_type
            FROM warehouses
            WHERE user_id = ?
        """, (user_id,))

        rows = cursor.fetchall()

        hub = None
        capitals = []

        for r in rows:
            node_type = (r["node_type"] or "").strip().lower()

            if "hub" in node_type:
                hub = r["name"] or r["city"]

            elif "capital" in node_type:
                capitals.append(r["name"] or r["city"])
        return hub, capitals
    
    except Exception as e:
        logger.error(f"Error getting hub and capitals: {str(e)}")
        return None
    finally:
        conn.close()


def multimodal_route_exists(route_id: int, user_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT 1
            FROM multimodal_routes
            WHERE route_id = ? AND user_id = ?
            LIMIT 1
        """, (route_id, user_id))

        return cursor.fetchone() is not None

    except Exception as e:
        logger.error(f"Error checking multimodal route existence: {str(e)}")
        return False

    finally:
        conn.close()

#================================= NEW ========================================================================================
def deactivate_multimodal_route(route_id: int, user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE multimodal_routes
            SET is_active = 0, updated_at = CURRENT_TIMESTAMP
            WHERE route_id = ? AND user_id = ?
        """, (route_id, user_id,))

        conn.commit()

    except Exception as e:
        logger.error(f"Error deactivating multimodal route {route_id}: {str(e)}")
        return None

    finally:
        conn.close()

def activate_multimodal_route(route_id: int, user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE multimodal_routes
            SET is_active = 1, updated_at = CURRENT_TIMESTAMP
            WHERE route_id = ? AND user_id = ?
        """, (route_id, user_id))

        conn.commit()

    except Exception as e:
        logger.error(f"Error activating multimodal route {route_id}: {str(e)}")
        return None

    finally:
        conn.close()


#============================================================================================================================

def fetch_persistent_routes_by_user(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        query = """
            SELECT 
                route_id,
                parent_route_id,
                route_data,
                is_active,
                created_at
            FROM persistent_routes
            WHERE user_id = ?
            ORDER BY created_at ASC
        """

        cursor.execute(query, (user_id,))
        rows = cursor.fetchall()

        routes = []
        for row in rows:
            routes.append({
                "route_id": row[0],
                "parent_route_id": row[1],
                "route_data": json.loads(row[2]),
                "is_active": bool(row[3]),
                "created_at": row[4]
            })

        return routes
    
    except Exception as e:
        logger.error(f"Error getting persistent route: {str(e)}")
        return []
    finally:
        conn.close()

def fetch_multimodal_routes_by_user(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        query = """
            SELECT 
                route_id,
                multimodal_data,
                source,
                destination,
                is_active,
                created_at
            FROM multimodal_routes
            WHERE user_id = ?
            ORDER BY created_at ASC
        """

        cursor.execute(query, (user_id,))
        rows = cursor.fetchall()

        routes = []
        for row in rows:
            routes.append({
                "route_id": row[0],
                "multimodal_data": json.loads(row[1]),
                "source": row[2],
                "destination": row[3],
                "is_active": bool(row[4]),
                "created_at": row[5]
            })

        return routes

    except Exception as e:
        logger.error(f"Error getting multimodal persistent route: {str(e)}")
        return []
    finally:
        conn.close()


# def get_route_id_by_source_dest(
#     user_id: int,
#     source: str,
#     destination: str,
#     intermediate_locations: list = None,
#     objective: str = "duration"
# ):
#     conn = get_db_connection()
#     cursor = conn.cursor()

#     try:
#         # ================================
#         # 1️⃣ Check Persistent Routes
#         # ================================
#         sql = """
#             SELECT route_id FROM persistent_routes
#             WHERE user_id = ?
#             AND source = ?
#             AND destination = ?
#             AND is_active = 1
#         """

#         params = [user_id, source, destination]

#         # Intermediate filter
#         if intermediate_locations is not None:
#             intermediate_json = json.dumps(intermediate_locations)
#             sql += " AND intermediate_locations = ?"
#             params.append(intermediate_json)
#         else:
#             sql += " AND (intermediate_locations IS NULL OR intermediate_locations = '[]')"

#         # Objective filter
#         if objective is not None:
#             sql += " AND LOWER(objective) = ?"
#             params.append(objective.lower())
#         else:
#             sql += " AND (objective IS NULL OR objective = '')"

#         sql += " LIMIT 1"

#         cursor.execute(sql, params)
#         row = cursor.fetchone()

#         if row:
#             return {
#                 "route_id": row["route_id"],
#                 "route_type": "persistent"
#             }

#         # ================================
#         # 2️⃣ Check Multimodal Routes
#         # ================================
#         query = """
#             SELECT route_id FROM multimodal_routes
#             WHERE user_id = ?
#             AND source = ?
#             AND destination = ?
#             AND is_active = 1
#         """

#         params = [user_id, source, destination]

#         if objective is not None:
#             query += " AND LOWER(objective) = ?"
#             params.append(objective.lower())
#         else:
#             query += " AND (objective IS NULL OR objective = '')"

#         query += " LIMIT 1"

#         cursor.execute(query, params)
#         row = cursor.fetchone()

#         if row:
#             return {
#                 "route_id": row["route_id"],
#                 "route_type": "multimodal"
#             }

#         # ================================
#         # 3️⃣ Not Found
#         # ================================
#         return None

#     except Exception as e:
#         logger.error(f"Error getting route by source/destination: {str(e)}")
#         return None
#     finally:
#         conn.close()


def get_route_id_by_source_dest(
    user_id: int,
    source: str,
    destination: str,
    intermediate_locations: list = None,
    objective: str = "duration",
    route_type: str = None
):
    """
    Retrieve a route ID from either persistent_routes or multimodal_routes
    using case‑insensitive matching on source, destination, objective, and
    (for persistent routes) intermediate locations.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # ==================== PERSISTENT ROUTES ====================
        # Fetch all matching persistent routes based on source/destination (case‑insensitive)
        sql = """
            SELECT route_id, intermediate_locations FROM persistent_routes
            WHERE user_id = ?
            AND LOWER(source) = LOWER(?)
            AND LOWER(destination) = LOWER(?)
            AND is_active = 1
        """
        params = [user_id, source, destination]

        if objective is not None:
            sql += " AND LOWER(objective) = LOWER(?)"
            params.append(objective)
        else:
            sql += " AND (objective IS NULL OR objective = '')"

        # Optionally filter by route_type if provided
        if route_type:
            sql += " AND LOWER(route_type) = LOWER(?)"
            params.append(route_type)

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        if rows:
            if intermediate_locations:
                norm_user_intermediate = [loc.lower() for loc in intermediate_locations]

                for row in rows:
                    stored = row["intermediate_locations"]

                    if stored:
                        stored_list = json.loads(stored) if isinstance(stored, str) else stored
                    else:
                        stored_list = []

                    norm_stored = [loc.lower() for loc in stored_list]

                    if norm_stored == norm_user_intermediate:
                        return {"route_id": row["route_id"], "route_type": "persistent"}
            else:
                # No intermediate filter provided → accept any match
                return {"route_id": rows[0]["route_id"], "route_type": "persistent"}

        # ==================== MULTIMODAL ROUTES ====================
        query = """
            SELECT route_id FROM multimodal_routes
            WHERE user_id = ?
            AND LOWER(source) = LOWER(?)
            AND LOWER(destination) = LOWER(?)
            AND is_active = 1
        """
        params = [user_id, source, destination]

        if route_type:
            query += " AND LOWER(route_type) = LOWER(?)"
            params.append(route_type)

        if objective is not None:
            query += " AND LOWER(objective) = LOWER(?)"
            params.append(objective)
        else:
            query += " AND (objective IS NULL OR objective = '')"

        query += " LIMIT 1"

        cursor.execute(query, params)
        row = cursor.fetchone()
        if row:
            return {"route_id": row["route_id"], "route_type": "multimodal"}

        return None

    except Exception as e:
        logger.error(f"Error getting route by source/destination: {str(e)}")
        return None
    finally:
        conn.close()


# def get_route_id_by_source_dest(
#     user_id: int,
#     source: str,
#     destination: str,
#     intermediate_locations: list = None,
#     objective: str = "duration",
#     route_type: str = None      
# ):
#     conn = get_db_connection()
#     cursor = conn.cursor()

#     try:
#         # ============================================================
#         # 1️⃣ Check Persistent Routes
#         # ============================================================
#         sql = """
#             SELECT route_id FROM persistent_routes
#             WHERE user_id = ?
#             AND source = ?
#             AND destination = ?
#             AND is_active = 1
#         """

#         params = [user_id, source, destination]

#         # Intermediate filter
#         if intermediate_locations:
#             intermediate_json = json.dumps(intermediate_locations)
#             sql += " AND intermediate_locations = ?"
#             params.append(intermediate_json)
    
#         # Apply route_type filter ONLY IF provided
#         if route_type:
#             sql += " AND LOWER(route_type) = ?"
#             params.append(route_type.lower())

#         # Objective filter
#         if objective is not None:
#             sql += " AND LOWER(objective) = ?"
#             params.append(objective.lower())
#         else:
#             sql += " AND (objective IS NULL OR objective = '')"

#         sql += " LIMIT 1"

#         cursor.execute(sql, params)
#         row = cursor.fetchone()

#         if row:
#             return {
#                 "route_id": row["route_id"],
#                 "route_type": "persistent"
#             }

#         # ============================================================
#         # 2️⃣ Check Multimodal Routes
#         # ============================================================
#         query = """
#             SELECT route_id FROM multimodal_routes
#             WHERE user_id = ?
#             AND source = ?
#             AND destination = ?
#             AND is_active = 1
#         """

#         params = [user_id, source, destination]

#         # Apply route_type filter ONLY IF provided
#         if route_type:
#             query += " AND LOWER(route_type) = ?"
#             params.append(route_type.lower())

#         # Objective filter
#         if objective is not None:
#             query += " AND LOWER(objective) = ?"
#             params.append(objective.lower())
#         else:
#             query += " AND (objective IS NULL OR objective = '')"

#         query += " LIMIT 1"

#         cursor.execute(query, params)
#         row = cursor.fetchone()

#         if row:
#             return {
#                 "route_id": row["route_id"],
#                 "route_type": "multimodal"
#             }

#         # ============================================================
#         # 3️⃣ Not Found → Return None
#         # ============================================================
#         return None

#     except Exception as e:
#         logger.error(f"Error getting route by source/destination: {str(e)}")
#         return None

#     finally:
#         conn.close()



def road_route_summary(user_id: int, route_id: int, from_loc: str, to_loc: str,
                             distance: float, duration: float, cost: float,
                             route_type: str = "road"):
    """
    Store lightweight summary of the route with user_id instead of auto id
    """

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO nodes
        (user_id, route_id, from_location, to_location, distance, duration, cost, route_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        route_id,
        from_loc,
        to_loc,
        distance,
       	duration,
        cost,
        route_type
    ))

    conn.commit()
    conn.close()

# ================================================================
# 1. LOAD ROUTE GRAPH FROM DB (route_summary)
# ================================================================
def load_edges_and_nodes(user_id: int):
    """
    Loads route_summary edges and builds:
    - nodes: dict(name -> dummy coords)
    - edges: dict((from,to) -> {from,to,distance,time,fuel})
    """

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            from_location, 
            to_location, 
            distance, 
            duration, 
            cost
        FROM nodes 
        WHERE user_id = ?
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()

    nodes = {}
    edges = {}

    for frm, to, dist, dur, fuel in rows:

        if frm not in nodes:
            nodes[frm] = (0, 0)
        if to not in nodes:
            nodes[to] = (0, 0)

        edges[(frm, to)] = {
            "from": frm,
            "to": to,
            "distance": dist,
            "time": dur,
            "fuel": fuel
        }

    return nodes, edges


def load_edges_and_nodes_air(user_id: int):
    """
    Loads route_summary edges and builds:
    - nodes: dict(name -> dummy coords)
    - edges: dict((from,to) -> {from,to,distance,time,fuel})
    """

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            from_location, 
            to_location, 
            distance, 
            duration, 
            cost
        FROM nodes_air 
        WHERE user_id = ?
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()

    nodes = {}
    edges = {}

    for frm, to, dist, dur, fuel in rows:

        if frm not in nodes:
            nodes[frm] = (0, 0)
        if to not in nodes:
            nodes[to] = (0, 0)

        edges[(frm, to)] = {
            "from": frm,
            "to": to,
            "distance": dist,
            "time": dur,
            "fuel": fuel
        }

    return nodes, edges


def air_route_summary(user_id: int, route_id: int, from_loc: str, to_loc: str,
                             distance: float, duration: float, cost: float,
                             route_type: str = "air"):
    """
    Store lightweight summary of the route with user_id instead of auto id
    """

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO nodes_air
        (user_id, route_id, from_location, to_location, distance, duration, cost, route_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        route_id,
        from_loc,
        to_loc,
        distance,
       	duration,
        cost,
        route_type
    ))

    conn.commit()
    conn.close()

def delete_nodes_by_user(user_id: int):
    """
    Deletes all rows from `nodes` table for the given user_id.
    Returns number of deleted rows.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM nodes WHERE user_id = ?", (user_id,))
        deleted_count = cursor.rowcount

        conn.commit()
        conn.close()
        return deleted_count

    except Exception as e:
        logger.error(f"Error deleting nodes for user {user_id}: {e}", exc_info=True)
        return 0

def delete_nodes_by_user_air(user_id: int):
    """
    Deletes all rows from `nodes` table for the given user_id.
    Returns number of deleted rows.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM nodes_air WHERE user_id = ?", (user_id,))
        deleted_count = cursor.rowcount

        conn.commit()
        conn.close()
        return deleted_count

    except Exception as e:
        logger.error(f"Error deleting nodes for user {user_id}: {e}", exc_info=True)
        return 0
    
def delete_nodes_by_route(user_id: int, route_id: int):
    """
    Delete all rows from `nodes` table for a specific user_id and route_id.
    Returns number of deleted rows.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM nodes 
            WHERE user_id = ? AND route_id = ?
        """, (user_id, route_id))

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted_count

    except Exception as e:
        logger.error(f"Error deleting nodes for user {user_id}, route {route_id}: {e}", exc_info=True)
        return 0


def delete_nodes_by_route_air(user_id: int, route_id: int):
    """
    Delete all rows from `nodes` table for a specific user_id and route_id.
    Returns number of deleted rows.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM nodes_air 
            WHERE user_id = ? AND route_id = ?
        """, (user_id, route_id))

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted_count

    except Exception as e:
        logger.error(f"Error deleting nodes for user {user_id}, route {route_id}: {e}", exc_info=True)
        return 0
    

# ──────────────────────────────────────────────────────────────────────────────
# 6.  DATABASE HELPER  (add to database.py)
# ──────────────────────────────────────────────────────────────────────────────

def combined_route_summary(
    user_id: int,
    route_id: int,
    from_loc: str,
    to_loc: str,
    distance: float,
    duration: float,
    cost: float,
    route_type: str
):
    """
    Store a route segment (road/air) into nodes_combined for the given user.
    """

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO nodes_combined
            (user_id, route_id, from_location, to_location, distance, duration, cost, route_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            route_id,
            from_loc,
            to_loc,
            distance,
            duration,
            cost,
            route_type
        ))

        conn.commit()
        return True

    except Exception as e:
        print(f"[ERROR] Failed to insert into nodes_combined for user={user_id}: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()

def get_nodes_by_user(user_id: int) -> list[dict]:
    """Return all route nodes (road + air) for the given user."""

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT route_id, from_location, to_location, distance, duration, cost, route_type
        FROM nodes_combined
        WHERE user_id = ?
        """,
        (user_id,)
    )

    rows = cursor.fetchall()

    keys = ["route_id", "from_location", "to_location", "distance", "duration", "cost", "route_type"]

    return [dict(zip(keys, row)) for row in rows]

def delete_nodes_combined_by_user(user_id: int) -> int:
    """
    Delete all route nodes from nodes_combined for the given user.
    Returns number of deleted rows.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM nodes_combined
            WHERE user_id = ?
            """,
            (user_id,)
        )

        affected = cursor.rowcount
        conn.commit()
        return affected

    except Exception as e:
        print(f"[ERROR] Failed to delete nodes_combined for user={user_id} | {e}")
        conn.rollback()
        return 0

    finally:
        conn.close()


def delete_nodes_combined_by_user_and_route(user_id: int, route_id: int) -> int:
    """
    Delete a specific route (by route_id) for the given user_id 
    from nodes_combined.
    Returns number of deleted rows (0 or 1).
    """

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM nodes_combined
            WHERE user_id = ? AND route_id = ?
            """,
            (user_id, route_id)
        )

        affected = cursor.rowcount
        conn.commit()
        return affected

    except Exception as e:
        print(f"[ERROR] Failed to delete route_id={route_id} for user={user_id} | {e}")
        conn.rollback()
        return 0

    finally:
        conn.close()

def delete_persistent_route_by_user_and_route(user_id: int, route_id: int) -> int:
    """
    Delete a specific route (by route_id) for the given user_id 
    from persistent_routes.
    Returns number of deleted rows (0 or 1).
    """

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM persistent_routes
            WHERE user_id = ? AND route_id = ?
            """,
            (user_id, route_id)
        )

        affected = cursor.rowcount
        conn.commit()

        if affected:
            logger.info(f"Deleted persistent route {route_id} for user {user_id}")
        else:
            logger.warning(f"No route found for deletion: route_id={route_id}, user_id={user_id}")

        return affected

    except Exception as e:
        logger.error(f"Failed to delete persistent route_id={route_id} for user={user_id} | {e}")
        conn.rollback()
        return 0

    finally:
        conn.close()

# ========================================================== Disruption ======================================================
# ========================================================== Disruption ======================================================


def get_warehouses_df(user_id: int) -> pd.DataFrame:
    conn = None
    try:
        conn = get_db_connection()
        df = pd.read_sql("""
            SELECT w.city AS City,
                   w.name AS Name,
                   wi.inventory AS Inventory,
                   wi.reorder_level AS ReorderLevel,
                   w.latitude,
                   w.longitude
            FROM warehouses w
            JOIN warehouse_inventory wi
                ON w.user_id = wi.user_id
                AND w.warehouse_id = wi.warehouse_id
            WHERE w.user_id = ? AND w.is_active = 1
        """, conn, params=(user_id,))
        return df
    except Exception as e:
        logger.error(f"Error fetching warehouses for user_id={user_id} | {e}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()


def get_city_coordinates(user_id: int) -> Dict[str, Tuple[float, float]]:
    """
    Returns {city_or_name_lower: (lat, lon)}.
    """
    conn = None
    try:
        conn = get_db_connection()
        df = pd.read_sql(
            "SELECT name, city, latitude, longitude FROM warehouses WHERE user_id = ? AND is_active = 1",
            conn, params=(user_id,)
        )

        city_map: Dict[str, Tuple[float, float]] = {}

        for _, row in df.iterrows():
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except (TypeError, ValueError):
                continue

            name = str(row["name"] or "").lower().strip()
            # city = str(row["city"] or "").lower().strip()

            if name:
                city_map[name] = (lat, lon)
            # if city:
            #     city_map[city] = (lat, lon)

        return city_map

    except Exception as e:
        logger.error(f"Error fetching city coordinates for user_id={user_id} | {e}")
        return {}

    finally:
        if conn:
            conn.close()



def get_road_routes_df(user_id: int) -> pd.DataFrame:
    """
    Columns: source_city, destination_city, lat_src, lon_src, lat_dst, lon_dst
    """
    conn = None
    try:
        conn = get_db_connection()
        nodes_df = pd.read_sql(
            "SELECT from_location, to_location FROM nodes WHERE user_id = ?",
            conn, params=(user_id,)
        )

        city_coords = get_city_coordinates(user_id)
        routes = []

        for _, row in nodes_df.iterrows():
            try:
                src = str(row["from_location"] or "").lower().strip()
                dst = str(row["to_location"] or "").lower().strip()

                if not src or not dst:
                    continue
                if src not in city_coords or dst not in city_coords:
                    continue

                lat_src, lon_src = city_coords[src]
                lat_dst, lon_dst = city_coords[dst]

                routes.append({
                    "source_city": src,
                    "destination_city": dst,
                    "lat_src": lat_src,
                    "lon_src": lon_src,
                    "lat_dst": lat_dst,
                    "lon_dst": lon_dst,
                })

            except Exception as inner_e:
                logger.warning(f"Skipping invalid route row | {inner_e}")
                continue

        _COLS = ["source_city", "destination_city", "lat_src", "lon_src", "lat_dst", "lon_dst"]
        return pd.DataFrame(routes) if routes else pd.DataFrame(columns=_COLS)

    except Exception as e:
        logger.error(f"Error fetching road routes for user_id={user_id} | {e}")
        return pd.DataFrame()

    finally:
        if conn:
            conn.close()


def get_vehicles_df(user_id: int) -> pd.DataFrame:
    conn = None
    try:
        conn = get_db_connection()
        df = pd.read_sql("""
            SELECT id AS vehicle_id,
                   type AS vehicle_type,
                   capacity AS capacity_kg,
                   current_location AS base_city,
                   schedule_departure_time AS departure_time,
                   arrival_time AS arrival_time
            FROM vehicles
            WHERE user_id = ? AND is_active = 1
        """, conn, params=(user_id,))
        return df
    except Exception as e:
        logger.error(f"Error fetching vehicles for user_id={user_id} | {e}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()


def _get_airport_coordinates(user_id, conn):
    query = """
        SELECT DISTINCT LOWER(warehouse_name) AS city,
                        latitude,
                        longitude
        FROM nearest_airports
        WHERE user_id = ?
    """
    df = pd.read_sql(query, conn, params=(user_id,))

    coord_map = {
        row["city"]: (row["latitude"], row["longitude"])
        for _, row in df.iterrows()
    }

    return coord_map


def get_air_routes_df(user_id: int) -> pd.DataFrame:
    conn = None
    try:
        conn = get_db_connection()
        # Fetch all air segments
        segments_df = pd.read_sql(
            "SELECT from_location, to_location FROM nodes_air WHERE user_id = ?",
            conn, params=(user_id,)
        )
        if segments_df.empty:
            return pd.DataFrame(columns=["source_airport", "destination_airport",
                                         "lat_src", "lon_src", "lat_dst", "lon_dst"])

        # Get airport coordinates
        airports_coords = _get_airport_coordinates(user_id, conn)

        routes = []
        for _, row in segments_df.iterrows():
            src = str(row["from_location"] or "").lower().strip()
            dst = str(row["to_location"] or "").lower().strip()
            if not src or not dst:
                continue
            if src not in airports_coords or dst not in airports_coords:
                continue
            lat_src, lon_src = airports_coords[src]
            lat_dst, lon_dst = airports_coords[dst]
            routes.append({
                "source_airport": src,
                "destination_airport": dst,
                "lat_src": lat_src,
                "lon_src": lon_src,
                "lat_dst": lat_dst,
                "lon_dst": lon_dst,
            })
        return pd.DataFrame(routes)
    except Exception as e:
        logger.error(f"Error fetching air routes for user_id={user_id}: {e}")
        return pd.DataFrame(columns=["source_airport", "destination_airport",
                                     "lat_src", "lon_src", "lat_dst", "lon_dst"])
    finally:
        if conn:
            conn.close()

def prepare_disruption_data(user_id: int):
    """Returns (warehouses_df, road_routes_df, vehicles_df, air_routes_df)."""
    try:
        warehouses_df = get_warehouses_df(user_id)
        road_routes_df = get_road_routes_df(user_id)
        vehicles_df = get_vehicles_df(user_id)
        air_routes_df = get_air_routes_df(user_id)
        return warehouses_df, road_routes_df, vehicles_df, air_routes_df
    except Exception as e:
        logger.error(f"Error preparing disruption data for user_id={user_id} | {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    



# def get_warehouses_df(user_id: int) -> pd.DataFrame:
#     """Columns: City, Name, Inventory, ReorderLevel"""
#     conn = None
#     try:
#         conn = get_db_connection()
#         df = pd.read_sql("""
#             SELECT
#                 w.city           AS City,
#                 w.name           AS Name,
#                 wi.inventory     AS Inventory,
#                 wi.reorder_level AS ReorderLevel
#             FROM warehouses w
#             JOIN warehouse_inventory wi
#                 ON  w.user_id      = wi.user_id
#                 AND w.warehouse_id = wi.warehouse_id
#             WHERE w.user_id = ? AND w.is_active = 1
#         """, conn, params=(user_id,))
        
#         return df

#     except Exception as e:
#         logger.error(f"Error fetching warehouses for user_id={user_id} | {e}")
#         return pd.DataFrame()

#     finally:
#         if conn:
#             conn.close()


# # ── 2. City coordinates ───────────────────────────────────────────────────────

# def get_city_coordinates(user_id: int) -> Dict[str, Tuple[float, float]]:
#     """
#     Returns {city_or_name_lower: (lat, lon)}.
#     """
#     conn = None
#     try:
#         conn = get_db_connection()
#         df = pd.read_sql(
#             "SELECT name, city, latitude, longitude FROM warehouses WHERE user_id = ? AND is_active = 1",
#             conn, params=(user_id,)
#         )

#         city_map: Dict[str, Tuple[float, float]] = {}

#         for _, row in df.iterrows():
#             try:
#                 lat = float(row["latitude"])
#                 lon = float(row["longitude"])
#             except (TypeError, ValueError):
#                 continue

#             name = str(row["name"] or "").lower().strip()
#             city = str(row["city"] or "").lower().strip()

#             if name:
#                 city_map[name] = (lat, lon)
#             if city:
#                 city_map[city] = (lat, lon)

#         return city_map

#     except Exception as e:
#         logger.error(f"Error fetching city coordinates for user_id={user_id} | {e}")
#         return {}

#     finally:
#         if conn:
#             conn.close()


# # ── 3. Road routes ────────────────────────────────────────────────────────────

# def get_road_routes_df(user_id: int) -> pd.DataFrame:
#     """
#     Columns: source_city, destination_city, lat_src, lon_src, lat_dst, lon_dst
#     """
#     conn = None
#     try:
#         conn = get_db_connection()
#         nodes_df = pd.read_sql(
#             "SELECT from_location, to_location FROM nodes WHERE user_id = ?",
#             conn, params=(user_id,)
#         )

#         city_coords = get_city_coordinates(user_id)
#         routes = []

#         for _, row in nodes_df.iterrows():
#             try:
#                 src = str(row["from_location"] or "").lower().strip()
#                 dst = str(row["to_location"] or "").lower().strip()

#                 if not src or not dst:
#                     continue
#                 if src not in city_coords or dst not in city_coords:
#                     continue

#                 lat_src, lon_src = city_coords[src]
#                 lat_dst, lon_dst = city_coords[dst]

#                 routes.append({
#                     "source_city": src,
#                     "destination_city": dst,
#                     "lat_src": lat_src,
#                     "lon_src": lon_src,
#                     "lat_dst": lat_dst,
#                     "lon_dst": lon_dst,
#                 })

#             except Exception as inner_e:
#                 logger.warning(f"Skipping invalid route row | {inner_e}")
#                 continue

#         _COLS = ["source_city", "destination_city", "lat_src", "lon_src", "lat_dst", "lon_dst"]
#         return pd.DataFrame(routes) if routes else pd.DataFrame(columns=_COLS)

#     except Exception as e:
#         logger.error(f"Error fetching road routes for user_id={user_id} | {e}")
#         return pd.DataFrame()

#     finally:
#         if conn:
#             conn.close()


# # ── 4. Vehicles ───────────────────────────────────────────────────────────────

# def get_vehicles_df(user_id: int) -> pd.DataFrame:
#     conn = None
#     try:
#         conn = get_db_connection()
#         df = pd.read_sql("""
#             SELECT id AS vehicle_id, type AS vehicle_type,
#                    capacity AS capacity_kg, current_location AS base_city
#             FROM vehicles WHERE user_id = ? AND is_active = 1
#         """, conn, params=(user_id,))

#         return df

#     except Exception as e:
#         logger.error(f"Error fetching vehicles for user_id={user_id} | {e}")
#         return pd.DataFrame()

#     finally:
#         if conn:
#             conn.close()


# # ── 5. Master ─────────────────────────────────────────────────────────────────

# def prepare_disruption_data(user_id: int):
#     """Returns (warehouses_df, road_routes_df, vehicles_df)."""
#     try:
#         warehouses_df = get_warehouses_df(user_id)
#         routes_df = get_road_routes_df(user_id)
#         vehicles_df = get_vehicles_df(user_id)

#         return warehouses_df, routes_df, vehicles_df

#     except Exception as e:
#         logger.error(f"Error preparing disruption data for user_id={user_id} | {e}")
#         return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
