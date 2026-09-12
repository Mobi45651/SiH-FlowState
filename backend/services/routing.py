import math, heapq, requests
from models import RouteSegment
from services.predict import predict
from services.weather import fetch
from flask import current_app

def dist(a,b,c,d):
    R=6371; p1=math.radians(a); p2=math.radians(c); dp=math.radians(c-a); dl=math.radians(d-b); x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2; return 2*R*math.asin(math.sqrt(x))
def nearest_node(lat,lng,nodes): return min(nodes,key=lambda n:dist(lat,lng,n[0],n[1]))
def build_graph(risks, safe_only=False, balanced=False):
    nodes={}; edges={}
    for s,r in risks:
        a=(round(s.start_lat,6),round(s.start_lng,6)); b=(round(s.end_lat,6),round(s.end_lng,6)); nodes[a]=a;nodes[b]=b
        blocked=safe_only and r['risk_category'] in ('HIGH','SEVERE')
        if blocked: continue
        base=s.length_km/max(.1,s.speed_kmh)*60
        penalty={'LOW':0,'MODERATE':2,'HIGH':8,'SEVERE':20}[r['risk_category']]
        w=base+(penalty if balanced else 0)
        edges.setdefault(a,[]).append((b,w,s,r)); edges.setdefault(b,[]).append((a,w,s,r))
    return list(nodes),edges
def shortest(edges,start,end):
    q=[(0,start)]; prev={}; seen={start:0}
    while q:
        d,u=heapq.heappop(q)
        if d!=seen.get(u): continue
        if u==end: break
        for v,w,s,r in edges.get(u,[]):
            nd=d+w
            if nd<seen.get(v,float('inf')): seen[v]=nd;prev[v]=(u,s,r);heapq.heappush(q,(nd,v))
    if end not in seen:return None
    path=[];u=end
    while u!=start: pu,s,r=prev[u]; path.append((s,r));u=pu
    path.reverse();return path,seen[end]
def calculate_route(fl,tl,mode='safe'):
    roads=RouteSegment.query.all(); risks=[]
    weather_cache={}
    for s in roads:
        z=s.zone_id
        zone=s.zone
        weather_cache.setdefault(z,fetch(zone.latitude,zone.longitude))
        risks.append((s,predict(s,zone,weather_cache[z],60)))
    nodes,edges=build_graph(risks,safe_only=(mode=='safe'),balanced=(mode=='balanced'))
    if not nodes:return {'error':'No road graph available'}
    start=nearest_node(fl[0],fl[1],nodes); end=nearest_node(tl[0],tl[1],nodes)
    result=shortest(edges,start,end)
    if not result and mode=='safe':
        nodes,edges=build_graph(risks,safe_only=False,balanced=True);result=shortest(edges,start,end)
    if not result:return {'error':'No route found'}
    path,cost=result; coords=[[s.start_lat,s.start_lng] for s,r in path]+([[path[-1][0].end_lat,path[-1][0].end_lng]] if path else [])
    total_km=sum(s.length_km for s,r in path); minutes=sum(s.length_km/max(.1,s.speed_kmh)*60 for s,r in path)
    return {'mode':mode,'distance_km':round(total_km,2),'duration_minutes':round(minutes,1),'risk':'LOW' if mode=='safe' else max((r['risk_category'] for s,r in path),default='LOW',key=lambda x:['LOW','MODERATE','HIGH','SEVERE'].index(x)),'path':[{'road':s.road_name,**r} for s,r in path],'coordinates':coords,'nodes_used':len(path)+1}
