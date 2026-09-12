from pathlib import Path
import numpy as np, joblib, math
from models import Drain
from services.weather import get_rain_window
MODEL_DIR=Path(__file__).resolve().parents[1]/'ml'/'saved_models'
FEATURES=['rain_1h','rain_3h','rain_6h','forecast_1h','forecast_3h','elevation_m','slope_percent','impervious_percent','drainage_utilization','blockage_percent','historical_risk','road_factor']
RISK=['LOW','MODERATE','HIGH','SEVERE']
def load_models():
    try: return joblib.load(MODEL_DIR/'flood_classifier.joblib'),joblib.load(MODEL_DIR/'depth_regressor.joblib')
    except Exception: return None,None
CLF,REG=load_models()
def nearest_drain_stats(zone_id):
    ds=Drain.query.filter_by(zone_id=zone_id).all()
    if not ds: return 0.8,0
    cap=sum(d.effective_capacity() for d in ds); blockage=sum(d.blockage_percent for d in ds)/len(ds)
    return cap,blockage
def risk_for(p,depth):
    if depth>=30 or p>=.85:return 'SEVERE'
    if depth>=15 or p>=.65:return 'HIGH'
    if depth>=5 or p>=.35:return 'MODERATE'
    return 'LOW'
def road_factor(road): return 1.28 if road.is_flood_prone else (1.12 if road.road_class in ('service','residential') else 1.0)
def predict(road,zone,weather,horizon):
    h=max(1,min(6,horizon//60 if horizon else 1)); rain1=sum(x['precipitation_mm'] for x in weather['hourly'][:1]); rain3=sum(x['precipitation_mm'] for x in weather['hourly'][:3]); rain6=sum(x['precipitation_mm'] for x in weather['hourly'][:6]); f1=sum(x['precipitation_mm'] for x in weather['hourly'][1:2]) if len(weather['hourly'])>1 else 0; f3=sum(x['precipitation_mm'] for x in weather['hourly'][1:4]) if len(weather['hourly'])>3 else 0
    cap,blockage=nearest_drain_stats(zone.id); area=max(.15,zone.area_km2); runoff=(rain3+f3)*area*zone.impervious_surface_percent/100*0.000278; util=runoff/max(cap,0.05)
    hist={'LOW':0,'MEDIUM':1,'HIGH':2}.get(zone.historical_flood_frequency,1)
    x=np.array([[rain1,rain3,rain6,f1,f3,zone.elevation_m,zone.slope_percent,zone.impervious_surface_percent,util,blockage,hist,road_factor(road)]])
    if CLF is not None:
        p=float(CLF.predict_proba(x)[0,1]); depth=float(REG.predict(x)[0])
    else:
        score=.025*rain1+.02*rain3+.03*f3+.65*zone.impervious_surface_percent/100+.7*util+.7*blockage/100+.45*hist+.45*(road_factor(road)-1); p=float(1/(1+math.exp(-(score-1.8)))); depth=float(max(0,(rain3+f3)*.18+util*7+blockage*.08+hist*4))
    # Forecast horizon increases standing-water estimate when rainfall is sustained.
    depth=max(0,depth*(1+0.08*(horizon/60)))
    return {'probability':min(.999,max(0,p)),'water_depth_cm':depth,'risk_category':risk_for(p,depth),'rainfall_mm':rain3+f3,'drainage_utilization':util,'source':'rf_hybrid' if CLF else 'rule_fallback'}
