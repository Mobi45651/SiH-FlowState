# FlowState Backend — Fixed Windows Setup

This package fixes the `NameError: DB_WRITE_LOCK is not defined` that occurred in the previous backend package and keeps the SQLite write protections.

## 1. Stop old Python/Flask processes

```powershell
taskkill /F /IM python.exe
```

If that says no process was found, continue.

## 2. Open this backend folder

```powershell
cd C:\SIH\backend
```

Make sure this is the `backend` folder from this ZIP.

## 3. Activate your existing virtual environment

```powershell
.\venv\Scripts\activate
```

If the venv does not exist, install dependencies first:

```powershell
pip install -r requirements.txt
```

## 4. Start exactly one Flask server

```powershell
python app.py
```

Do not start a second Flask/Python process against the same SQLite database.

## 5. Test

Open:

```text
http://localhost:5000/api/health
```

Then change the dashboard location. Normal GET requests must no longer regenerate alerts/nowcasts.

## Important

The screenshot error was:

`NameError: name 'DB_WRITE_LOCK' is not defined`

The cause was a missing import in `services/rainfall_pipeline.py`. This package includes the missing import.


## Weather accuracy fix

This build requests the **nearest Open-Meteo grid cell** for each monitoring
coordinate and returns the provider grid coordinates in the API response.
Open-Meteo documents that the returned grid-cell coordinate can differ from
the requested coordinate; `cell_selection=nearest` selects the nearest
possible cell.

If you are replacing only the code but keeping an older SQLite database, run:

```powershell
flask --app app fix-gurugram-coordinates
```

Then restart Flask. The weather response can be inspected at:

```text
http://localhost:5000/api/weather?zone_id=1&refresh=1
```

Look at `weather.latitude`, `weather.longitude`, `weather.provider_latitude`,
`weather.provider_longitude`, and `weather.current.temperature_2m`.

The backend does **not** add a fake correction such as `+7°C`. Any remaining
difference is therefore attributable to the weather provider/model/grid and
can be measured from the returned metadata.
