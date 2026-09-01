AUTO_CONFIG = {
        "speed": 50,
        "fuel_type": "Diesel",
        "fuel_consumption": 25,
        "fuel_price": 0.95,
        "backendTypes": ["autos", "auto", "three_wheeler"]
}

CAR_CONFIG = {
        "speed": 100,
        "fuel_type": "Petrol",
        "fuel_consumption": 15,
        "fuel_price": 1.2,
        "backendTypes": ["cars", "car"]
}

TRUCK_CONFIG = {
        "speed": 80,
        "fuel_type": "Diesel",
        "fuel_consumption": 7,
        "fuel_price": 0.95,
        "backendTypes": ["trucks", "truck"]
}

BIKE_CONFIG = {
        "speed": 60,
        "fuel_type": "Petrol",
        "fuel_consumption": 40,
        "fuel_price": 1.2,
        "backendTypes": ["bikes", "bike"]
}

PLANE_CONFIG = {
        "speed": 800,                    
        "fuel_type": "ATF",              
        "fuel_consumption": 0.5,        
        "fuel_price": 1.2,              
        "backendTypes": ["planes", "plane", "aircraft"]
}

VEHICLE_TYPES = {
        "auto": AUTO_CONFIG,
        "autos": AUTO_CONFIG,
        "car": CAR_CONFIG,
        "cars": CAR_CONFIG,
        "bike": BIKE_CONFIG,
        "bikes": BIKE_CONFIG,
        "truck": TRUCK_CONFIG,
        "trucks": TRUCK_CONFIG,
        "plane": PLANE_CONFIG,
        "planes": PLANE_CONFIG,
        "aircraft": PLANE_CONFIG
}
