"""Reproducible demo assumptions; no proprietary input or external service."""
import csv
import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / 'intellifleet-web-main/frontendmain/public/synthetic_v2'
CITIES = [
('Delhi',28.6139,77.2090,'North','DEL'),('Mumbai',19.0760,72.8777,'West','BOM'),
('Bengaluru',12.9716,77.5946,'South','BLR'),('Chennai',13.0827,80.2707,'South','MAA'),
('Kolkata',22.5726,88.3639,'East','CCU'),('Hyderabad',17.3850,78.4867,'South','HYD'),
('Pune',18.5204,73.8567,'West','PNQ'),('Ahmedabad',23.0225,72.5714,'West','AMD'),
('Jaipur',26.9124,75.7873,'North','JAI'),('Lucknow',26.8467,80.9462,'North','LKO'),
('Kanpur',26.4499,80.3319,'North','KNU'),('Varanasi',25.3176,82.9739,'North','VNS'),
('Indore',22.7196,75.8577,'Central','IDR'),('Udaipur',24.5854,73.7125,'West','UDR'),
('Ludhiana',30.9010,75.8573,'North',''),('Mohali',30.7046,76.7179,'North','IXC'),
('Kochi',9.9312,76.2673,'South','COK'),('Coimbatore',11.0168,76.9558,'South','CJB'),
('Madurai',9.9252,78.1198,'South','IXM'),('Surat',21.1702,72.8311,'West','STV'),
('Nagpur',21.1458,79.0882,'Central','NAG'),('Bhopal',23.2599,77.4126,'Central','BHO'),
('Patna',25.5941,85.1376,'East','PAT'),('Ranchi',23.3441,85.3096,'East','IXR'),
('Bhubaneswar',20.2961,85.8245,'East','BBI'),('Visakhapatnam',17.6868,83.2185,'South','VTZ'),
('Vijayawada',16.5062,80.6480,'South','VGA'),('Guwahati',26.1445,91.7362,'Northeast','GAU'),
('Siliguri',26.7271,88.3953,'East','IXB'),('Dehradun',30.3165,78.0322,'North','DED')]

def write(name, rows):
    with (OUT/name).open('w', newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def distance(a,b):
    a,b=CITIES[a],CITIES[b]
    x,y,u,v=map(math.radians,(a[1],a[2],b[1],b[2]))
    return 12742*math.asin(math.sqrt(math.sin((u-x)/2)**2+math.cos(x)*math.cos(u)*math.sin((v-y)/2)**2))

def generate():
    OUT.mkdir(parents=True,exist_ok=True)
    warehouses=[]
    for i,(city,lat,lng,region,airport) in enumerate(CITIES):
        warehouses.append(dict(WarehouseID=f'WH-{i+1:03}',Country='India',City=city,NodeType='Gateway' if i<6 else 'Hub',Name=city,
            Address=f'Synthetic logistics node, {city}, India',Latitude=lat,Longitude=lng,Inventory=12000+i*200,ReorderLevel=3000,
            StorageCapacity=40000+i*1000,ReservedInventory=1000,HandlingCostPerUnitINR=2.5,FixedOperatingCostPerDayINR=12000,
            ReliabilityScore=.96,DisruptionRiskScore=.04,NearestAirportIATA=airport,AirportDistanceKm=30 if airport else '',
            Region=region,AnnualDemandUnits=300000,PrimarySKU='DEMO-PARCEL',Status='active',data_source='SYNTHETIC'))
    # Payloads are conservative demo class assumptions, not manufacturer specifications.
    classes=[('BharatBenz linehaul',16000,34,55,3000,90),('Tata Ultra',7000,24,48,1800,60),
             ('Eicher Pro',5000,21,45,1400,45),('Tata 407',2000,16,40,650,30),('Tata Ace',750,10,35,250,20),
             ('Ashok Leyland Partner',3500,19,42,1000,40)]
    vehicles=[]
    for i in range(97):
        # Each facility has a useful linehaul/medium fleet before supplementary local vans.
        model,cap,cost,speed,rng,load=classes[i//30 if i<90 else 3+(i%3)]
        vehicles.append(dict(VehicleID=f'TRK-{i+1:03}',WarehouseName=CITIES[i%30][0],VehicleType='Truck',VehicleModel=model,
            VehicleCapacity=cap,DepartureTime='00:00',Mode='road',Status='available',CostPerKmINR=cost,CostPerHourINR=120,
            FixedDispatchCostINR=500,AvgSpeedKmph=speed,MaxRangeKm=rng,LoadingTimeMin=load,UnloadingTimeMin=load,
            ReliabilityScore=.96,BreakdownRiskScore=.03,CO2KgPerKm=.8,ExpressEligible='true',Refrigerated='false',data_source='SYNTHETIC'))
    for i in range(6):
        vehicles[90+i].update(VehicleID=f'AIR-{i+1:03}',WarehouseName=CITIES[i][0],VehicleType='Plane',VehicleModel='Demo regional cargo aircraft allocation',
            VehicleCapacity=12000,Mode='air',CostPerKmINR=70,CostPerHourINR=2000,FixedDispatchCostINR=10000,AvgSpeedKmph=650,
            MaxRangeKm=3500,LoadingTimeMin=60,UnloadingTimeMin=60,CO2KgPerKm=8)
    pairs=[(0,8),(8,13),(13,7),(7,19),(19,1),(1,6),(6,5),(5,2),(2,3),(2,17),(17,16),(17,18),
           (0,9),(9,10),(10,11),(11,22),(22,4),(4,23),(23,24),(24,25),(25,26),(26,5),
           (0,15),(15,14),(0,29),(7,12),(12,21),(21,20),(20,5),(4,28),(28,27),(0,1),(1,2)]
    routes=[]
    for a,b in pairs:
        for a,b in [(a,b),(b,a)]:
            d=round(distance(a,b)*1.22)
            speed=32 if 29 in (a,b) or 27 in (a,b) else 40 if d<250 else 52 if d<800 else 58
            buffer=.5 if d<250 else 1 if d<800 else 2
            duration=round((d/speed+buffer)*60)
            routes.append(dict(RouteID=f'R-{len(routes)+1:03}',Source=CITIES[a][0],Destination=CITIES[b][0],IntermediateLocation='',
                RouteType='road',DistanceKm=d,TypicalDurationMin=duration,BaseTransportCostINR=d*28,EffectiveSpeedKmph=round(d/(duration/60),2),
                RouteClass='hilly' if speed==32 else 'regional' if speed==40 else 'intercity' if speed==52 else 'linehaul',
                OperationalBufferMin=buffer*60,ReliabilityScore=.95,WeatherRiskScore=.05,DisruptionRiskScore=.04,
                CapacityPerDayKg=64000,CurrentUtilizationPct=35,ServiceClass='standard',ExpressEligible='true',SLAHours=round(duration/60+4,2),
                TollCostINR=round(d*2),Status='active',data_source='SYNTHETIC'))
    for a,b in [(0,1),(1,2),(2,4),(4,0),(3,5),(5,0)]:
        d=round(distance(a,b)); duration=round((d/650+1)*60)
        row=dict(routes[0]); row.update(RouteID=f'R-{len(routes)+1:03}',Source=CITIES[a][0],Destination=CITIES[b][0],RouteType='air',
            DistanceKm=d,TypicalDurationMin=duration,BaseTransportCostINR=d*70,EffectiveSpeedKmph=round(d/(duration/60),2),
            RouteClass='air',OperationalBufferMin=60,SLAHours=round(duration/60+3,2),TollCostINR=0)
        routes.append(row)
    schedules=[]
    for a,b in [(13,0),(0,1),(1,2),(2,3),(4,0),(5,3)]:
        for mode in ['AIR','SURFACE','RAIL']:
            for run,etd in [('1',20*60),('2',23*60)]:
                d=round(distance(a,b)*(1 if mode=='AIR' else 1.22))
                tt=round((d/(650 if mode=='AIR' else 52 if mode=='SURFACE' else 48)+(1 if mode=='AIR' else 2))*60)
                eta=etd+tt
                schedules.append(dict(schedule_id=f'SYN-{len(schedules)+1:03}',origin_city=CITIES[a][0],origin_station=f'SYN-{CITIES[a][4]}-STN',
                    gateway=f'SYN-{CITIES[b][4]}-GTW',lane=f'{CITIES[a][0]} -> {CITIES[b][0]}',run=run,mode=mode,
                    service=f'DEMO-{mode}-{run}',cutoff=f'{etd//60-2:02}:00',etd=f'{etd//60:02}:00',eta=f'{eta%1440//60:02}:{eta%60:02}',
                    eta_day_offset=eta//1440,retrieval_or_tt=tt,operating_template='DAILY_DEMO',data_source='SYNTHETIC',
                    origin_latitude=CITIES[a][1],origin_longitude=CITIES[a][2],destination_latitude=CITIES[b][1],destination_longitude=CITIES[b][2]))
    write('warehouse.csv',warehouses); write('vehicle.csv',vehicles); write('routes.csv',routes); write('schedules.csv',schedules)

if __name__=='__main__': generate()
