import asyncio
import io
import json
import math
import sqlite3
import time

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend.config.config import settings
from backend.routes.auth import get_current_user
from backend.utilities.geocode import geocode_address

router = APIRouter(tags=["Network Ingestion"])

def _value(row, name, default=None):
    value=row.get(name,default)
    return default if pd.isna(value) else value

def _bool(value) -> int:
    return int(str(value).strip().casefold() in {"1","true","yes","y","active","available"})


def _csv(data: bytes) -> pd.DataFrame:
    frame = pd.read_csv(io.StringIO(data.decode("utf-8")))
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame


def _require(frame: pd.DataFrame, columns: set[str], label: str):
    missing = columns - set(frame.columns)
    if missing:
        raise HTTPException(422, f"{label} CSV missing columns: {', '.join(sorted(missing))}")


def _distance(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371 * 2 * math.asin(math.sqrt(h))


@router.post("/upload-network")
async def upload_network(
    warehouse_csv: UploadFile = File(...), vehicle_csv: UploadFile = File(...), routes_csv: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    started = time.perf_counter(); user_id = current_user["user_id"]
    warehouses, vehicles, routes = await asyncio.gather(warehouse_csv.read(), vehicle_csv.read(), routes_csv.read())
    wf, vf, rf = _csv(warehouses), _csv(vehicles), _csv(routes)
    _require(wf, {"Name","Address","Country","City","NodeType","Inventory","ReorderLevel"}, "Warehouse")
    _require(vf, {"WarehouseName","VehicleType","VehicleCapacity","DepartureTime"}, "Vehicle")
    _require(rf, {"Source","Destination","IntermediateLocation","RouteType"}, "Routes")
    names = {str(x).strip() for x in wf["Name"]}
    missing_vehicle = sorted({str(x).strip() for x in vf["WarehouseName"]} - names)
    intermediate_names=set()
    for value in rf["IntermediateLocation"]:
        if pd.notna(value) and str(value).strip(): intermediate_names.update(x.strip(" []") for x in str(value).replace("|",",").split(",") if x.strip(" []"))
    route_names = {str(x).strip() for x in rf["Source"]} | {str(x).strip() for x in rf["Destination"]} | intermediate_names
    missing_route = sorted(route_names - names)
    if missing_vehicle or missing_route:
        raise HTTPException(422, {"missing_vehicle_warehouses": missing_vehicle, "missing_route_warehouses": missing_route})
    if wf["Name"].astype(str).str.strip().duplicated().any():
        raise HTTPException(422, "Warehouse names must be unique")

    coords = {}
    has_coords = {"Latitude","Longitude"} <= set(wf.columns)
    if has_coords:
        for _, row in wf.iterrows(): coords[str(row["Name"]).strip()] = (float(row["Latitude"]),float(row["Longitude"]))
    elif settings.GOOGLE_MAPS_API_KEY:
        unique = {str(row["Address"]).strip() for _,row in wf.iterrows()}
        resolved = await asyncio.gather(*(asyncio.to_thread(geocode_address,address) for address in unique))
        address_coords = dict(zip(unique,resolved))
        for _,row in wf.iterrows(): coords[str(row["Name"]).strip()] = address_coords[str(row["Address"]).strip()]
    else:
        raise HTTPException(422,"Warehouse CSV needs Latitude/Longitude when GOOGLE_MAPS_API_KEY is unavailable")
    if any(not a or a[0] is None or a[1] is None for a in coords.values()):
        raise HTTPException(422,"One or more warehouse coordinates could not be resolved")

    warnings=[]; route_rows=[]
    for index,row in rf.iterrows():
        source,destination=str(row["Source"]).strip(),str(row["Destination"]).strip(); mode=str(row["RouteType"]).strip().lower()
        if mode not in {"road","air"}: raise HTTPException(422,f"Unsupported RouteType at row {index+2}: {mode}")
        straight=_distance(coords[source],coords[destination]); distance=float(row["DistanceKm"]) if "DistanceKm" in rf.columns and pd.notna(row["DistanceKm"]) else straight*(1.22 if mode=="road" else 1.0)
        duration=(float(row["TypicalDurationMin"])/60 if "TypicalDurationMin" in rf.columns and pd.notna(row["TypicalDurationMin"])
                  else float(row["DurationHours"]) if "DurationHours" in rf.columns and pd.notna(row["DurationHours"]) else distance/(60 if mode=="road" else 700)+(.5 if mode=="air" else 0))
        cost=(float(row["BaseTransportCostINR"]) if "BaseTransportCostINR" in rf.columns and pd.notna(row["BaseTransportCostINR"])
              else float(row["Cost"]) if "Cost" in rf.columns and pd.notna(row["Cost"]) else distance*(15 if mode=="road" else 52))
        external_route_id=str(_value(row,"RouteID",f"R-{index+1:03d}")); route_record_id=index+1; intermediate=[] if pd.isna(row["IntermediateLocation"]) else [x.strip(" []") for x in str(row["IntermediateLocation"]).replace("|",",").split(",") if x.strip(" []")]
        points=[source,*intermediate,destination]
        for leg_index,(leg_source,leg_destination) in enumerate(zip(points,points[1:])):
            leg_id=route_record_id*100+leg_index if len(points)>2 else route_record_id
            share=_distance(coords[leg_source],coords[leg_destination])/max(.001,sum(_distance(coords[a],coords[b]) for a,b in zip(points,points[1:])))
            route_rows.append((user_id,leg_id,leg_source,leg_destination,round(distance*share,2),round(duration*share,2),round(cost*share,2),mode,row,external_route_id,route_record_id,intermediate))
    supplied_distance="DistanceKm" in rf.columns
    supplied_duration="TypicalDurationMin" in rf.columns or "DurationHours" in rf.columns
    supplied_cost="BaseTransportCostINR" in rf.columns or "Cost" in rf.columns
    if not (supplied_distance and supplied_duration and supplied_cost): warnings.append("Missing route metrics were deterministically estimated from coordinates and mode")

    try:
        with sqlite3.connect("users.db") as conn:
            conn.execute("PRAGMA foreign_keys=ON"); conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM route_conditions WHERE user_id=?",(user_id,))
            conn.execute("DELETE FROM nodes WHERE user_id=?",(user_id,)); conn.execute("DELETE FROM nodes_air WHERE user_id=?",(user_id,))
            conn.execute("DELETE FROM persistent_routes WHERE user_id=?",(user_id,)); conn.execute("DELETE FROM multimodal_routes WHERE user_id=?",(user_id,))
            conn.execute("DELETE FROM vehicles WHERE user_id=?",(user_id,)); conn.execute("DELETE FROM warehouse_inventory WHERE user_id=?",(user_id,))
            conn.execute("DELETE FROM nearest_airports WHERE user_id=?",(user_id,)); conn.execute("DELETE FROM warehouses WHERE user_id=?",(user_id,))
            warehouse_rows=[]; inventory_rows=[]
            for index,row in wf.iterrows():
                wid=index+1; name=str(row["Name"]).strip(); lat,lng=coords[name]
                active=_bool(_value(row,"Status","active"))
                warehouse_rows.append((wid,user_id,str(row["Country"]).strip(),str(row["City"]).strip(),str(row["NodeType"]).strip(),name,str(row["Address"]).strip(),lat,lng,active))
                capacity=float(_value(row,"StorageCapacity",0)); reserved=float(_value(row,"ReservedInventory",0)); handling=float(_value(row,"HandlingCostPerUnitINR",_value(row,"HandlingCost",0)))
                inventory_rows.append((user_id,wid,name,int(row["Inventory"]),int(row["ReorderLevel"]),capacity,reserved,handling,
                    float(_value(row,"FixedOperatingCostPerDayINR",0)),float(_value(row,"ReliabilityScore",.9)),float(_value(row,"DisruptionRiskScore",0)),
                    _value(row,"NearestAirportIATA"),_value(row,"AirportDistanceKm"),_value(row,"Region"),_value(row,"AnnualDemandUnits"),_value(row,"PrimarySKU")))
            conn.executemany("INSERT INTO warehouses(warehouse_id,user_id,country,city,node_type,name,address,latitude,longitude,is_active) VALUES(?,?,?,?,?,?,?,?,?,?)",warehouse_rows)
            conn.executemany("INSERT INTO warehouse_inventory(user_id,warehouse_id,warehouse_name,inventory,reorder_level,storage_capacity,reserved_inventory,handling_cost,fixed_operating_cost,reliability,disruption_risk,nearest_airport_iata,airport_distance_km,region,annual_demand_units,primary_sku) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",inventory_rows)
            name_ids={row[5]:row[0] for row in warehouse_rows}; vehicle_rows=[]
            for index,row in vf.iterrows():
                typ=str(row["VehicleType"]).strip(); label=str(_value(row,"VehicleID",_value(row,"VehicleLabel",f"{typ}_{index+1}"))); status=str(_value(row,"Status","available"))
                vehicle_rows.append((user_id,name_ids[str(row["WarehouseName"]).strip()],typ,label,int(row["VehicleCapacity"]),str(row["WarehouseName"]).strip(),_bool(status),status,str(row["DepartureTime"]),
                    float(_value(row,"CostPerKmINR",_value(row,"CostPerKm",0))),float(_value(row,"ReliabilityScore",_value(row,"Reliability",.9))),str(_value(row,"Mode",typ)),
                    float(_value(row,"CostPerHourINR",0)),float(_value(row,"FixedDispatchCostINR",0)),_value(row,"AvgSpeedKmph"),float(_value(row,"BreakdownRiskScore",0)),
                    _value(row,"AvailableFrom"),_value(row,"AvailableUntil"),_value(row,"MaxRangeKm"),float(_value(row,"LoadingTimeMin",0)),float(_value(row,"UnloadingTimeMin",0)),
                    float(_value(row,"CO2KgPerKm",0)),_bool(_value(row,"ExpressEligible",False)),_bool(_value(row,"Refrigerated",False))))
            conn.executemany("INSERT INTO vehicles(user_id,warehouse_id,type,label,capacity,current_location,is_available,status,schedule_departure_time,cost_per_km,reliability,compatible_modes,cost_per_hour,fixed_dispatch_cost,avg_speed_kmph,breakdown_risk,available_from,available_until,max_range_km,loading_time_min,unloading_time_min,co2_kg_per_km,express_eligible,refrigerated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",vehicle_rows)
            road=[x[:8] for x in route_rows if x[7]=="road"]; air=[x[:8] for x in route_rows if x[7]=="air"]
            conn.executemany("INSERT INTO nodes(user_id,route_id,from_location,to_location,distance,duration,cost,route_type) VALUES(?,?,?,?,?,?,?,?)",road)
            conn.executemany("INSERT INTO nodes_air(user_id,route_id,from_location,to_location,distance,duration,cost,route_type) VALUES(?,?,?,?,?,?,?,?)",air)
            conditions=[]
            for user,route_id,source,dest,distance,duration,cost,mode,row,external_id,record_id,intermediate in route_rows:
                status=str(_value(row,"Status","active")); conditions.append((user,route_id,float(_value(row,"ReliabilityScore",.9)),float(_value(row,"WeatherRiskScore",0)),float(_value(row,"DisruptionRiskScore",0)),float(_value(row,"TollCostINR",0)),0,0,cost if mode=="air" else 0,
                    _value(row,"CapacityPerDayKg"),_value(row,"CurrentUtilizationPct"),_value(row,"ServiceClass"),_bool(_value(row,"ExpressEligible",False)),_value(row,"SLAHours"),_value(row,"CarbonKg"),status,_value(row,"Notes"),cost))
            conn.executemany("INSERT INTO route_conditions(user_id,route_id,reliability,weather_risk,operational_risk,toll_cost,handling_cost,fuel_cost,air_cost,capacity_per_day_kg,current_utilization_pct,service_class,express_eligible,sla_hours,carbon_kg,status,notes,base_transport_cost) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",conditions)
            persistent=[]
            for index,row in rf.iterrows():
                record_id=index+1; source=str(row["Source"]).strip(); destination=str(row["Destination"]).strip(); mode=str(row["RouteType"]).strip().lower()
                intermediate=[] if pd.isna(row["IntermediateLocation"]) else [x.strip(" []") for x in str(row["IntermediateLocation"]).replace("|",",").split(",") if x.strip(" []")]
                external_id=str(_value(row,"RouteID",f"R-{record_id:03d}")); distance=float(row["DistanceKm"]); duration=float(row["TypicalDurationMin"])/60
                cost=float(row["BaseTransportCostINR"]); locations=[source,*intermediate,destination]
                path=[{"lat":coords[name][0],"lng":coords[name][1]} for name in locations]
                data={"route_id":record_id,"external_route_id":external_id,"source":source,"destination":destination,
                      "intermediate_locations":intermediate,"locations":locations,"route_type":mode,"distance":distance,
                      "duration":duration,"route_cost":cost,"optimal_routes":[{"path":path,"distance":distance,"duration":duration,"isOptimal":True}],
                      "service_class":_value(row,"ServiceClass"),"sla_hours":_value(row,"SLAHours")}
                active=_bool(_value(row,"Status","active"))
                persistent.append((record_id,user_id,json.dumps(data),json.dumps(locations),source,destination,json.dumps(intermediate),"balanced",active,mode))
            conn.executemany("INSERT INTO persistent_routes(route_id,user_id,route_data,waypoints,source,destination,intermediate_locations,objective,is_active,route_type) VALUES(?,?,?,?,?,?,?,?,?,?)",persistent)
    except Exception as exc:
        raise HTTPException(500,f"Network import rolled back: {exc}") from exc
    road_count=int((rf["RouteType"].astype(str).str.lower()=="road").sum()); air_count=int((rf["RouteType"].astype(str).str.lower()=="air").sum())
    active_count=int(rf["Status"].map(_bool).sum()) if "Status" in rf.columns else len(rf)
    return {"success":True,"warehouses":len(wf),"vehicles":len(vf),"routes":len(rf),"active_routes":active_count,
            "road_routes":road_count,"air_routes":air_count,"multimodal_routes":0,"graph_legs":len(route_rows),
            "processing_time_ms":round((time.perf_counter()-started)*1000,2),"warnings":warnings}
