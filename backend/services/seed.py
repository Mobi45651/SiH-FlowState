from extensions import db
from models import User,Zone,Drain,RouteSegment
from math import radians,sin,cos,asin,sqrt
ZONES=[
('Z01','Cyber City',28.4942,77.0888,232,1.8,91,5.0,'HIGH'),('Z02','DLF Phase 1',28.4702,77.1010,228,1.2,86,4.2,'HIGH'),('Z03','Sector 29',28.4660,77.0650,224,0.9,94,3.6,'HIGH'),('Z04','Sector 31',28.4500,77.0550,222,1.1,90,3.1,'MEDIUM'),('Z05','Sector 40',28.4420,77.0540,220,0.8,93,3.0,'MEDIUM'),('Z06','Sector 44',28.4507,77.0626,223,1.0,95,2.7,'HIGH'),('Z07','Sector 46',28.4375,77.0430,219,0.7,92,2.8,'MEDIUM'),('Z08','Sector 52',28.4445,77.0955,225,1.3,88,3.8,'MEDIUM'),('Z09','Sector 56',28.4250,77.1050,228,1.6,84,4.0,'MEDIUM'),('Z10','Sector 57',28.4210,77.0870,224,1.0,90,3.2,'HIGH'),('Z11','Sector 62',28.4020,77.0910,220,1.2,87,4.0,'MEDIUM'),('Z12','Golf Course Road',28.4455,77.1000,231,2.2,92,5.5,'HIGH'),('Z13','Palam Vihar',28.5070,77.0430,228,0.8,82,5.0,'MEDIUM'),('Z14','Badshahpur',28.4090,77.0560,218,1.4,79,6.0,'HIGH'),('Z15','Sohna Road',28.4140,77.0410,216,1.0,85,5.0,'MEDIUM'),('Z16','Manesar',28.3570,76.9390,245,2.8,74,7.0,'LOW')]
ROADS=[
('MG Road',28.4702,77.1010,28.4800,77.0950,'Z02',1.35,45,'arterial',True),('MG Road',28.4800,77.0950,28.4942,77.0888,'Z01',1.72,45,'arterial',True),('Golf Course Road',28.4455,77.1000,28.4550,77.0920,'Z12',1.32,50,'arterial',True),('Golf Course Road',28.4550,77.0920,28.4702,77.1010,'Z02',2.10,50,'arterial',False),('Sohna Road',28.4140,77.0410,28.4300,77.0500,'Z15',2.10,45,'arterial',True),('Sohna Road',28.4300,77.0500,28.4420,77.0540,'Z05',1.45,45,'arterial',True),('Sector 29 Main Road',28.4660,77.0650,28.4660,77.0800,'Z03',1.48,35,'urban',True),('Sector 29 Main Road',28.4660,77.0800,28.4702,77.1010,'Z02',2.10,35,'urban',False),('NH 48 Service Road',28.4942,77.0888,28.5070,77.0430,'Z01',5.20,40,'service',True),('Huda City Centre Road',28.4507,77.0626,28.4660,77.0650,'Z06',1.75,35,'urban',False),('Sector 44 Road',28.4507,77.0626,28.4420,77.0540,'Z06',1.35,35,'urban',True),('Sector 46 Road',28.4375,77.0430,28.4420,77.0540,'Z07',1.20,30,'residential',False),('Sector 40 Road',28.4420,77.0540,28.4500,77.0550,'Z05',0.95,30,'residential',False),('Sector 31 Road',28.4500,77.0550,28.4660,77.0650,'Z04',1.90,30,'urban',True),('Golf Course Ext Road',28.4250,77.1050,28.4445,77.0955,'Z09',2.40,40,'arterial',False),('Sector 56 Road',28.4250,77.1050,28.4210,77.0870,'Z09',2.05,30,'urban',True),('Sector 57 Road',28.4210,77.0870,28.4375,77.0430,'Z10',4.80,35,'urban',False),('Sector 62 Road',28.4020,77.0910,28.4250,77.1050,'Z11',3.10,40,'arterial',False),('Badshahpur Road',28.4090,77.0560,28.4140,77.0410,'Z14',1.75,35,'urban',True),('Palam Vihar Road',28.5070,77.0430,28.4942,77.0888,'Z13',5.20,40,'arterial',False)]
def seed(app):
    with app.app_context():
        db.create_all()
        if not User.query.first():
            u=User(email=app.config['ADMIN_EMAIL'],username='Authority Admin',role='admin');u.set_password(app.config['ADMIN_PASSWORD']);db.session.add(u)
        if Zone.query.first(): db.session.commit(); return
        zones={}
        for code,name,lat,lng,elev,slope,imp,area,hist in ZONES:
            z=Zone(zone_code=code,name=name,latitude=lat,longitude=lng,elevation_m=elev,slope_percent=slope,impervious_surface_percent=imp,area_km2=area,historical_flood_frequency=hist);db.session.add(z);zones[code]=z
        db.session.flush()
        for code,z in zones.items():
            for i in range(3):
                d=Drain(drain_code=f'{code}-D{i+1}',zone_id=z.id,latitude=z.latitude+(i-1)*.002,longitude=z.longitude+(i-1)*.0025,normal_capacity_m3s=1.2+i*.5,blockage_percent=[18,35,52][i] if z.historical_flood_frequency=='HIGH' else [8,18,28][i],condition='GOOD' if i==0 else 'FAIR');d.status='CRITICAL' if d.blockage_percent>50 else ('WARNING' if d.blockage_percent>30 else 'NORMAL');db.session.add(d)
        for name,slat,slng,elat,elng,zcode,length,speed,cls,flood in ROADS:
            db.session.add(RouteSegment(road_name=name,start_lat=slat,start_lng=slng,end_lat=elat,end_lng=elng,zone_id=zones[zcode].id,length_km=length,speed_kmh=speed,road_class=cls,is_flood_prone=flood,source='gurugram_demo_network'))
        db.session.commit()
