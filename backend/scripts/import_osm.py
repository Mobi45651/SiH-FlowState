"""Import Gurugram road segments from OpenStreetMap via Overpass.

Usage from backend directory:
    python scripts/import_osm.py

This replaces the demo RouteSegment rows with real OSM road geometry inside
the configured bounding box. It intentionally stores each consecutive OSM
way node pair as a RouteSegment so the existing Dijkstra engine has a
connected graph. Risk is initially LOW and is overwritten by the live zone
nowcast when routes are requested.
"""
import argparse, math, sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app
from extensions import db
from models import Zone, RouteSegment

OVERPASS = "https://overpass-api.de/api/interpreter"
DEFAULT_BBOX = (28.30, 76.85, 28.60, 77.20)  # south,west,north,east

def hav(lat1,lon1,lat2,lon2):
    r=6371.0; p1=math.radians(lat1); p2=math.radians(lat2)
    a=math.sin((p2-p1)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 2*r*math.asin(math.sqrt(a))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--south',type=float,default=DEFAULT_BBOX[0]); ap.add_argument('--west',type=float,default=DEFAULT_BBOX[1]); ap.add_argument('--north',type=float,default=DEFAULT_BBOX[2]); ap.add_argument('--east',type=float,default=DEFAULT_BBOX[3]); ap.add_argument('--limit',type=int,default=25000)
    a=ap.parse_args()
    q=f'''[out:json][timeout:90];way[highway]({a.south},{a.west},{a.north},{a.east});out tags geom;'''
    r=requests.post(OVERPASS,data=q,timeout=120); r.raise_for_status(); payload=r.json()
    app=create_app()
    with app.app_context():
        zones=Zone.query.all()
        RouteSegment.query.delete(); db.session.flush()
        count=0
        for el in payload.get('elements',[]):
            geom=el.get('geometry') or []
            tags=el.get('tags') or {}
            name=tags.get('name') or tags.get('ref') or f"OSM {el.get('id')}"
            for x,y in zip(geom,geom[1:]):
                if count>=a.limit: break
                lat1,lon1=x['lat'],x['lon']; lat2,lon2=y['lat'],y['lon']
                if not zones: continue
                zone=min(zones,key=lambda z:hav((lat1+lat2)/2,(lon1+lon2)/2,z.latitude,z.longitude))
                db.session.add(RouteSegment(road_name=name,start_lat=lat1,start_lng=lon1,end_lat=lat2,end_lng=lon2,zone_id=zone.id,risk_category='LOW',distance_km=max(0.01,hav(lat1,lon1,lat2,lon2)),is_flood_prone=False)); count+=1
            if count>=a.limit: break
        db.session.commit(); print(f'Imported {count} real OSM road segments.')

if __name__=='__main__': main()
