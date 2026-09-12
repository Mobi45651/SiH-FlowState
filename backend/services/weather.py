import time, requests
from flask import current_app
CACHE={}
class WeatherError(Exception): pass
def fetch(lat,lng):
    key=(round(lat,3),round(lng,3)); now=time.time(); hit=CACHE.get(key)
    if hit and now-hit[0] < current_app.config['WEATHER_CACHE_SECONDS']: return {**hit[1],'source':'open-meteo-cache'}
    params={'latitude':lat,'longitude':lng,'hourly':'precipitation,precipitation_probability,temperature_2m,rain,showers','current':'temperature_2m,relative_humidity_2m,precipitation,rain,showers,wind_speed_10m,weather_code','forecast_days':2,'timezone':'Asia/Kolkata'}
    try:
        r=requests.get(current_app.config['WEATHER_API_URL'],params=params,timeout=10); r.raise_for_status(); p=r.json()
        if 'hourly' not in p or 'time' not in p['hourly']: raise WeatherError('Malformed Open-Meteo response')
        h=p['hourly']; times=h['time']; prec=h.get('precipitation',[0]*len(times)); prob=h.get('precipitation_probability',[0]*len(times))
        hourly=[{'time':times[i],'precipitation_mm':float(prec[i] or 0),'precipitation_probability':float(prob[i] or 0)} for i in range(min(len(times),12))]
        data={'current':p.get('current',{}),'hourly':hourly,'timezone':p.get('timezone','Asia/Kolkata'),'source':'open-meteo'}
    except Exception as e:
        # Demo fallback is deliberately labelled.
        base=max(0.0,float(0.0))
        hourly=[]
        for i in range(12): hourly.append({'time':f'demo+{i}h','precipitation_mm':base,'precipitation_probability':0})
        data={'current':{'temperature_2m':30,'relative_humidity_2m':70,'precipitation':0,'rain':0,'showers':0,'wind_speed_10m':10,'weather_code':0},'hourly':hourly,'timezone':'Asia/Kolkata','source':'demo-fallback','error':str(e)}
    CACHE[key]=(now,data); return data

def get_rain_window(weather,hours): return sum(x['precipitation_mm'] for x in weather['hourly'][:hours])
