from datetime import datetime,timezone
from flask import Blueprint,jsonify,request,current_app
from itsdangerous import URLSafeTimedSerializer,BadSignature,SignatureExpired
from extensions import db
from models import User,Zone,Drain,RouteSegment,FloodPrediction,Alert
from services.weather import fetch
from services.predict import predict
from services.routing import calculate_route
bp=Blueprint('api',__name__)
def token_for(user): return URLSafeTimedSerializer(current_app.config['SECRET_KEY']).dumps({'id':user.id,'role':user.role})
def current_user():
    h=request.headers.get('Authorization','')
    if not h.startswith('Bearer '): return None
    try:return User.query.get(URLSafeTimedSerializer(current_app.config['SECRET_KEY']).loads(h[7:],max_age=86400)['id'])
    except (BadSignature,SignatureExpired,Exception):return None
def require_admin():
    u=current_user();return u if u and u.role=='admin' else None
@bp.get('/health')
def health(): return jsonify({'status':'ok','city':'Gurugram','timezone':'Asia/Kolkata','time':datetime.now(timezone.utc).isoformat()})
@bp.post('/auth/login')
def login():
    b=request.get_json() or {};u=User.query.filter_by(email=str(b.get('email','')).lower()).first()
    if not u or not u.check_password(str(b.get('password',''))): return jsonify({'error':'Invalid credentials'}),401
    return jsonify({'data':{'user':u.to_dict(),'token':token_for(u)}})
@bp.get('/zones')
def zones(): return jsonify({'data':[z.to_dict() for z in Zone.query.order_by(Zone.name).all()]})
@bp.get('/weather')
def weather():
    z=Zone.query.get(request.args.get('zone_id',type=int)) or Zone.query.first();w=fetch(z.latitude,z.longitude);return jsonify({'data':w,'zone':z.to_dict()})
@bp.get('/roads')
def roads():
    roads=RouteSegment.query.order_by(RouteSegment.road_name).all();out=[]
    cache={}
    for s in roads:
        z=s.zone
        if z.id not in cache: cache[z.id]=fetch(z.latitude,z.longitude)
        r=predict(s,z,cache[z.id],60);out.append(s.to_dict(r))
    return jsonify({'data':out,'meta':{'city':'Gurugram','source':'hybrid_prediction','street_level':True}})
@bp.get('/roads/<int:road_id>')
def road(road_id):
    s=RouteSegment.query.get_or_404(road_id);w=fetch(s.zone.latitude,s.zone.longitude);return jsonify({'data':s.to_dict(predict(s,s.zone,w,60))})
@bp.get('/roads/<int:road_id>/forecast')
def road_forecast(road_id):
    s=RouteSegment.query.get_or_404(road_id);w=fetch(s.zone.latitude,s.zone.longitude);items=[]
    for h in (0,30,60,90,120,150,180): items.append({'horizon_minutes':h,**predict(s,s.zone,w,h)})
    return jsonify({'data':items,'road':s.to_dict()})
@bp.get('/drains')
def drains(): return jsonify({'data':[d.to_dict() for d in Drain.query.order_by(Drain.drain_code).all()]})
@bp.post('/drains/<int:drain_id>/blockage')
def blockage(drain_id):
    if not require_admin(): return jsonify({'error':'Admin authentication required'}),403
    d=Drain.query.get_or_404(drain_id);b=float((request.get_json() or {}).get('blockage_percent',d.blockage_percent));d.blockage_percent=max(0,min(100,b));d.status='CRITICAL' if d.blockage_percent>=50 else ('WARNING' if d.blockage_percent>=30 else 'NORMAL');db.session.commit();return jsonify({'data':d.to_dict()})
@bp.post('/routes/safe')
def route():
    b=request.get_json() or {}
    try: fl=(float(b['from_lat']),float(b['from_lng']));tl=(float(b['to_lat']),float(b['to_lng']))
    except Exception:return jsonify({'error':'from_lat/from_lng/to_lat/to_lng required'}),400
    mode=b.get('mode','safe');return jsonify({'data':calculate_route(fl,tl,mode)})
def compute_alerts():
    Alert.query.update({'active':False});created=0;roads=RouteSegment.query.all();cache={}
    for s in roads:
        if s.zone_id not in cache: cache[s.zone_id]=fetch(s.zone.latitude,s.zone.longitude)
        for h in (60,120,180):
            r=predict(s,s.zone,cache[s.zone_id],h)
            if r['risk_category'] in ('HIGH','SEVERE'):
                sev=r['risk_category'];msg=f"{s.road_name}: {sev} waterlogging risk expected in {h//60}h; predicted depth {r['water_depth_cm']:.1f} cm.";db.session.add(Alert(road_id=s.id,zone_id=s.zone_id,severity=sev,horizon_minutes=h,message=msg,active=True));created+=1
                break
    db.session.commit();return {'new_or_refreshed_alerts':created}
@bp.post('/alerts/refresh')
def refresh_alerts():
    if not require_admin():return jsonify({'error':'Admin authentication required'}),403
    return jsonify({'data':compute_alerts()})
@bp.get('/alerts')
def alerts(): return jsonify({'data':[a.to_dict() for a in Alert.query.filter_by(active=True).order_by(Alert.severity.desc(),Alert.horizon_minutes).all()]})
@bp.get('/dashboard')
def dashboard():
    roads=RouteSegment.query.all();cache={};stats={'LOW':0,'MODERATE':0,'HIGH':0,'SEVERE':0};
    for s in roads:
        cache.setdefault(s.zone_id,fetch(s.zone.latitude,s.zone.longitude));stats[predict(s,s.zone,cache[s.zone_id],60)['risk_category']]+=1
    return jsonify({'data':{'zones':Zone.query.count(),'roads':len(roads),'drains':Drain.query.count(),'active_alerts':Alert.query.filter_by(active=True).count(),'risk_counts':stats,'model':'Random Forest + drainage physics','prediction_horizon_hours':3}})
@bp.get('/admin')
def admin():
    if not require_admin():return jsonify({'error':'Admin authentication required'}),403
    return dashboard()
