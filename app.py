import os
from dotenv import load_dotenv

load_dotenv()

import secrets
from flask import Flask, render_template, request, redirect, g, flash, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3
from datetime import date, datetime
import requests

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or "dev-secret-change-me"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_SAMESITE="Lax",
)
DATABASE = "farm.db"


def backup_database():
    import glob, os, shutil, time
    if not os.path.isfile(DATABASE):
        return
    os.makedirs("backups", exist_ok=True)
    target = "backups/farm-" + time.strftime("%Y%m%d") + ".db"
    if not os.path.exists(target):
        shutil.copy2(DATABASE, target)
    for old in sorted(glob.glob("backups/farm-*.db"))[:-14]:
        os.remove(old)


backup_database()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def validate_csrf():
    if request.method == "POST":
        expected = session.get("csrf_token", "")
        submitted = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(expected.encode(), submitted.encode()):
            abort(400)


# ---------- DB helpers ----------
def get_database():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_database(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---------- Utility helpers ----------
def normalize_email(value):
    return (value or "").strip().lower()


def require_int(value, field_name):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {field_name}.")


def require_float(value, field_name):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {field_name}.")


def require_date(value, field_name):
    try:
        if value in (None, ""):
            raise ValueError
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        raise ValueError(f"Invalid {field_name}.")


def parse_optional_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def form_data(*required_fields, optional=None):
    optional = optional or []
    data = {}
    missing = []

    for field in required_fields:
        value = (request.form.get(field, "") or "").strip()
        if not value:
            missing.append(field)
        data[field] = value

    for field in optional:
        data[field] = (request.form.get(field, "") or "").strip()

    if missing:
        raise ValueError(f"Missing required field(s): {', '.join(missing)}")
    return data


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return view_func(*args, **kwargs)

    return wrapped


def current_user_id():
    return session.get("user_id")


def user_owns_farm(user_id, farm_id):
    connection = get_database()
    row = connection.execute(
        "SELECT 1 FROM farms WHERE farm_id = ? AND user_id = ?",
        (farm_id, user_id),
    ).fetchone()
    return row is not None


def user_owns_field(user_id, field_id):
    connection = get_database()
    row = connection.execute(
        "SELECT 1 FROM fields f JOIN farms fm ON fm.farm_id = f.farm_id WHERE f.field_id = ? AND fm.user_id = ?",
        (field_id, user_id),
    ).fetchone()
    return row is not None


def user_owns_crop(user_id, crop_id):
    connection = get_database()
    row = connection.execute(
        "SELECT 1 FROM crops c JOIN farms f ON f.farm_id = c.farm_id WHERE c.crop_id = ? AND f.user_id = ?",
        (crop_id, user_id),
    ).fetchone()
    return row is not None


def user_owns_harvest(user_id, harvest_id):
    connection = get_database()
    row = connection.execute(
        "SELECT 1 FROM harvests h JOIN farms f ON f.farm_id = h.farm_id WHERE h.harvest_id = ? AND f.user_id = ?",
        (harvest_id, user_id),
    ).fetchone()
    return row is not None


def user_owns_product(user_id, product_id):
    connection = get_database()
    row = connection.execute(
        "SELECT 1 FROM product_history p JOIN farms f ON f.farm_id = p.farm_id WHERE p.product_id = ? AND f.user_id = ?",
        (product_id, user_id),
    ).fetchone()
    return row is not None


def validate_farm_selection(farm_id, user_id):
    farm_id = require_int(farm_id, "farm_id")
    if not user_owns_farm(user_id, farm_id):
        raise ValueError("Invalid farm selected.")
    return farm_id


def validate_field_selection(field_id, farm_id, user_id):
    field_id = require_int(field_id, "field_id")
    farm_id = require_int(farm_id, "farm_id")
    connection = get_database()
    row = connection.execute(
        "SELECT 1 FROM fields WHERE field_id = ? AND farm_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)",
        (field_id, farm_id, user_id),
    ).fetchone()
    if row is None:
        raise ValueError("Invalid field selected.")
    return field_id, farm_id


def validate_crop_selection(crop_id, farm_id, user_id):
    crop_id = require_int(crop_id, "crop_id")
    farm_id = require_int(farm_id, "farm_id")
    connection = get_database()
    row = connection.execute(
        "SELECT 1 FROM crops WHERE crop_id = ? AND farm_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)",
        (crop_id, farm_id, user_id),
    ).fetchone()
    if row is None:
        raise ValueError("Invalid crop selected.")
    return crop_id, farm_id


def validate_harvest_selection(harvest_id, farm_id, user_id):
    harvest_id = require_int(harvest_id, "harvest_id")
    farm_id = require_int(farm_id, "farm_id")
    connection = get_database()
    row = connection.execute(
        "SELECT 1 FROM harvests WHERE harvest_id = ? AND farm_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)",
        (harvest_id, farm_id, user_id),
    ).fetchone()
    if row is None:
        raise ValueError("Invalid harvest selected.")
    return harvest_id, farm_id


# ---------- Helpers for page data ----------
def crop_progress(planting_date, harvest_date):
    try:
        today = date.today()
        plant = date.fromisoformat(planting_date)
        harvest = date.fromisoformat(harvest_date)

        total_days = (harvest - plant).days
        elapsed_days = (today - plant).days
        days_left = (harvest - today).days

        if total_days <= 0:
            percent = 100
        else:
            percent = int((elapsed_days / total_days) * 100)
            percent = max(0, min(percent, 100))

        return percent, max(days_left, 0)
    except Exception:
        return 0, 0


def time_ago(date_str):
    try:
        activity_date = date.fromisoformat(date_str)
        delta_days = (date.today() - activity_date).days

        if delta_days <= 0:
            return "Today"
        elif delta_days == 1:
            return "1 day ago"
        elif delta_days < 7:
            return f"{delta_days} days ago"
        elif delta_days < 14:
            return "1 week ago"
        else:
            return f"{delta_days // 7} weeks ago"
    except Exception:
        return "Recently"


def get_market_insights(market_area_id):
    connection = get_database()

    total = connection.execute(
        """
        SELECT COUNT(*) FROM crops c
        JOIN farms f ON c.farm_id = f.farm_id
        WHERE c.status = 'growing' AND f.market_area_id = ?
        """,
        (market_area_id,),
    ).fetchone()[0]

    if total == 0:
        return []

    rows = connection.execute(
        """
        SELECT c.crop_name, COUNT(*) as crop_count
        FROM crops c
        JOIN farms f ON c.farm_id = f.farm_id
        WHERE c.status = 'growing' AND f.market_area_id = ?
        GROUP BY c.crop_name
        ORDER BY crop_count DESC
        """,
        (market_area_id,),
    ).fetchall()

    insights = []
    for row in rows:
        percent = round((row["crop_count"] / total) * 100)
        insights.append({
            "crop_name": row["crop_name"],
            "count": row["crop_count"],
            "percent": percent,
        })

    return insights


OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")

CROP_ICONS = {
    "potato": "🥔", "potatoes": "🥔",
    "maize": "🌽", "corn": "🌽",
    "beans": "🫘", "bean": "🫘",
    "tomato": "🍅", "tomatoes": "🍅",
    "onion": "🧅", "onions": "🧅",
    "cabbage": "🥬", "kale": "🥬", "spinach": "🥬",
    "carrot": "🥕", "carrots": "🥕",
    "wheat": "🌾", "rice": "🌾", "sorghum": "🌾", "millet": "🌾",
    "banana": "🍌", "avocado": "🥑", "pepper": "🌶️", "capsicum": "🌶️",
    "coffee": "☕", "tea": "🍃",
    "cassava": "🍠", "sugarcane": "🎋", "groundnut": "🥜", "peanut": "🥜",
    "sunflower": "🌻",
}


def get_crop_icon(crop_name):
    if not crop_name:
        return "🌱"
    name = crop_name.lower()
    for keyword, icon in CROP_ICONS.items():
        if keyword in name:
            return icon
    return "🌱"


app.jinja_env.filters["crop_icon"] = get_crop_icon


def get_notification_icon(message):
    if not message:
        return "🔔"
    text = message.lower()
    for keyword, icon in CROP_ICONS.items():
        if keyword in text:
            return icon
    if "weather" in text or "rain" in text or "wind" in text or "frost" in text:
        return "⚠️"
    if "harvest" in text:
        return "🌾"
    if "planted" in text or "planting" in text:
        return "🌱"
    return "🔔"


app.jinja_env.filters["notification_icon"] = get_notification_icon

ACTIVITY_ICONS = {
    "fertilizer": "🧪", "fertilizer application": "🧪",
    "irrigation": "💧", "watering": "💧",
    "weeding": "🌿", "pest": "🐛", "spraying": "🧴",
    "harvest": "🌾", "planting": "🌱", "pruning": "✂️",
    "soil test": "🧫",
}


def get_activity_icon(activity_type):
    if not activity_type:
        return "📋"
    name = activity_type.lower()
    for keyword, icon in ACTIVITY_ICONS.items():
        if keyword in name:
            return icon
    return "📋"


app.jinja_env.filters["activity_icon"] = get_activity_icon


def get_weather(lat, lon):
    try:
        if OPENWEATHER_API_KEY is None:
            return None
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&units=metric&appid={OPENWEATHER_API_KEY}"
        response = requests.get(url, timeout=5)
        data = response.json()
        return {
            "temp": round(data["main"]["temp"]),
            "description": data["weather"][0]["description"].title(),
            "icon": data["weather"][0]["icon"],
        }
    except Exception:
        return None


def get_forecast(lat, lon):
    try:
        if OPENWEATHER_API_KEY is None:
            return []
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=metric&appid={OPENWEATHER_API_KEY}"
        response = requests.get(url, timeout=5)
        data = response.json()
        return data.get("list", [])
    except Exception:
        return []


def summarize_daily_forecast(forecast_list):
    days = {}
    for entry in forecast_list:
        dt_txt = entry.get("dt_txt", "")
        if not dt_txt:
            continue
        date_str = dt_txt.split(" ")[0]
        days.setdefault(date_str, []).append(entry)

    icon_map = {
        "01": "☀️", "02": "🌤️", "03": "☁️", "04": "☁️",
        "09": "🌧️", "10": "🌦️", "11": "⛈️", "13": "❄️", "50": "🌫️",
    }

    summaries = []
    for date_str in sorted(days.keys())[:5]:
        entries = days[date_str]
        temps = [e["main"]["temp"] for e in entries if "main" in e]
        if not temps:
            continue
        high = round(max(temps))
        low = round(min(temps))
        pops = [e.get("pop", 0) for e in entries]
        rain_percent = round(max(pops) * 100) if pops else 0

        midday = min(
            entries,
            key=lambda e: abs(int(e.get("dt_txt", "00:00:00").split(" ")[1].split(":")[0]) - 12),
        )
        icon_code = midday["weather"][0]["icon"][:2] if midday.get("weather") else "01"
        icon = icon_map.get(icon_code, "🌤️")

        day_obj = datetime.strptime(date_str, "%Y-%m-%d")
        day_label = "Today" if day_obj.date() == datetime.now().date() else day_obj.strftime("%a")

        summaries.append({
            "day_label": day_label,
            "high": high,
            "low": low,
            "icon": icon,
            "rain_percent": rain_percent,
        })

    return summaries


def create_notification(user_id, message):
    connection = get_database()
    connection.execute(
        "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
        (user_id, message),
    )
    connection.commit()


def check_weather_alerts(farm_id, user_id, lat, lon):
    forecast_list = get_forecast(lat, lon)
    if not forecast_list:
        return

    upcoming = forecast_list[:8]

    heavy_rain = False
    max_wind = 0
    min_temp = 100

    for entry in upcoming:
        rain_volume = entry.get("rain", {}).get("3h", 0)
        if rain_volume >= 10:
            heavy_rain = True
        wind_speed = entry.get("wind", {}).get("speed", 0)
        max_wind = max(max_wind, wind_speed)
        temp = entry.get("main", {}).get("temp", 100)
        min_temp = min(min_temp, temp)

    connection = get_database()
    recent = connection.execute(
        """
        SELECT COUNT(*) FROM notifications
        WHERE user_id = ? AND message LIKE '%weather alert%'
        AND created_at >= datetime('now', '-12 hours')
        """,
        (user_id,),
    ).fetchone()[0]

    if recent > 0:
        return

    if heavy_rain:
        create_notification(user_id, "⚠️ Weather alert: Heavy rain expected in the next 24 hours. Consider delaying fertilizer application.")
    elif max_wind >= 10:
        create_notification(user_id, "⚠️ Weather alert: Strong winds expected in the next 24 hours.")
    elif min_temp <= 5:
        create_notification(user_id, "⚠️ Weather alert: Low temperatures expected — frost risk for sensitive crops.")


# ---------- Auth routes ----------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        try:
            data = form_data("full_name", "email", "password", optional=["phone"])
            data["email"] = normalize_email(data["email"])
            if len(data["password"]) < 6:
                raise ValueError("Password must be at least 6 characters.")
            if len(data["full_name"]) < 2:
                raise ValueError("Full name is too short.")
        except ValueError as e:
            flash(str(e))
            return render_template("signup.html")

        connection = get_database()

        existing = connection.execute(
            "SELECT * FROM users WHERE email = ?",
            (data["email"],),
        ).fetchone()

        if existing:
            flash("An account with that email already exists.")
            return render_template("signup.html")

        password_hash = generate_password_hash(data["password"])
        connection.execute(
            """
            INSERT INTO users (full_name, email, phone, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (data["full_name"], data["email"], data["phone"] or None, password_hash),
        )
        connection.commit()

        user = connection.execute(
            "SELECT * FROM users WHERE email = ?",
            (data["email"],),
        ).fetchone()

        session.clear()
        session["user_id"] = user["user_id"]
        session["full_name"] = user["full_name"]

        return redirect("/")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            data = form_data("email", "password")
            data["email"] = normalize_email(data["email"])
        except ValueError as e:
            flash(str(e))
            return render_template("login.html")

        connection = get_database()
        user = connection.execute(
            "SELECT * FROM users WHERE email = ?",
            (data["email"],),
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], data["password"]):
            flash("Incorrect email or password.")
            return render_template("login.html")

        session.clear()
        session["user_id"] = user["user_id"]
        session["full_name"] = user["full_name"]
        return redirect("/")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.context_processor
def inject_unread_count():
    if "user_id" not in session:
        return {"unread_count": 0}
    connection = get_database()
    count = connection.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0",
        (current_user_id(),),
    ).fetchone()[0]
    return {"unread_count": count}


# ---------- Main app routes ----------
@app.route("/")
@login_required
def home():
    connection = get_database()
    user_id = current_user_id()

    farm_with_location = connection.execute(
        """
        SELECT * FROM farms WHERE user_id = ? AND latitude IS NOT NULL LIMIT 1
        """,
        (user_id,),
    ).fetchone()

    weather = None
    daily_forecast = []
    if farm_with_location:
        weather = get_weather(farm_with_location["latitude"], farm_with_location["longitude"])
        daily_forecast = summarize_daily_forecast(get_forecast(farm_with_location["latitude"], farm_with_location["longitude"]))
        user_row = connection.execute(
            "SELECT weather_alerts_enabled FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if user_row and user_row["weather_alerts_enabled"]:
            check_weather_alerts(farm_with_location["farm_id"], user_id, farm_with_location["latitude"], farm_with_location["longitude"])

    farm_count = connection.execute(
        "SELECT COUNT(*) FROM farms WHERE user_id = ?",
        (user_id,),
    ).fetchone()[0]

    crop_count = connection.execute(
        """
        SELECT COUNT(*) FROM crops
        WHERE status = 'growing'
        AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (user_id,),
    ).fetchone()[0]

    soil_count = connection.execute(
        """
        SELECT COUNT(*) FROM soil_tests
        WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (user_id,),
    ).fetchone()[0]

    field_count = connection.execute(
        """
        SELECT COUNT(*) FROM fields
        WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (user_id,),
    ).fetchone()[0]

    activity_count = connection.execute(
        """
        SELECT COUNT(*) FROM activities
        WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (user_id,),
    ).fetchone()[0]

    harvest_count = connection.execute(
        """
        SELECT COUNT(*) FROM harvests
        WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (user_id,),
    ).fetchone()[0]

    product_count = connection.execute(
        """
        SELECT COUNT(*) FROM product_history
        WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (user_id,),
    ).fetchone()[0]

    raw_crops = connection.execute(
        """
        SELECT c.crop_name, c.planting_date, c.expected_harvest_date, f.field_name
        FROM crops c
        LEFT JOIN fields f ON c.field_id = f.field_id
        WHERE c.status = 'growing'
        AND c.farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        ORDER BY c.expected_harvest_date ASC
        LIMIT 4
        """,
        (user_id,),
    ).fetchall()

    crops_nearing_harvest = []
    for c in raw_crops:
        percent, days_left = crop_progress(c["planting_date"], c["expected_harvest_date"])
        crops_nearing_harvest.append({
            "crop_name": c["crop_name"],
            "field_name": c["field_name"],
            "percent": percent,
            "days_left": days_left,
            "icon": get_crop_icon(c["crop_name"]),
        })

    raw_activities = connection.execute(
        """
        SELECT a.activity_type, a.crop_name, a.activity_date, f.field_name, fa.farm_name
        FROM activities a
        LEFT JOIN crops c ON a.crop_id = c.crop_id
        LEFT JOIN fields f ON c.field_id = f.field_id
        LEFT JOIN farms fa ON a.farm_id = fa.farm_id
        WHERE a.farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        ORDER BY a.activity_date DESC
        LIMIT 4
        """,
        (user_id,),
    ).fetchall()

    recent_activities = []
    for a in raw_activities:
        recent_activities.append({
            "activity_type": a["activity_type"],
            "crop_name": a["crop_name"],
            "field_name": a["field_name"],
            "farm_name": a["farm_name"],
            "time_ago": time_ago(a["activity_date"]),
        })

    farm_for_market = connection.execute(
        "SELECT * FROM farms WHERE user_id = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    market_insights_data = []
    if farm_for_market and farm_for_market["market_area_id"]:
        raw_insights = get_market_insights(farm_for_market["market_area_id"])
        for item in raw_insights[:4]:
            if item["percent"] >= 40:
                supply_class, supply_label = "high", "High supply expected"
            elif item["percent"] >= 25:
                supply_class, supply_label = "moderate", "Moderate supply"
            else:
                supply_class, supply_label = "low", "Lower supply expected"
            market_insights_data.append({
                "crop_name": item["crop_name"],
                "percent": item["percent"],
                "supply_class": supply_class,
                "supply_label": supply_label,
                "icon": get_crop_icon(item["crop_name"]),
            })

    return render_template(
        "index.html",
        farm_count=farm_count,
        crop_count=crop_count,
        soil_count=soil_count,
        field_count=field_count,
        activity_count=activity_count,
        harvest_count=harvest_count,
        product_count=product_count,
        crops_nearing_harvest=crops_nearing_harvest,
        recent_activities=recent_activities,
        weather=weather,
        market_insights=market_insights_data,
        daily_forecast=daily_forecast,
    )


@app.route("/notifications")
@login_required
def notifications():
    connection = get_database()
    notes = connection.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
        (current_user_id(),),
    ).fetchall()

    connection.execute(
        "UPDATE notifications SET is_read = 1 WHERE user_id = ?",
        (current_user_id(),),
    )
    connection.commit()

    return render_template("notifications.html", notifications=notes)


@app.route("/market-insights")
@login_required
def market_insights():
    connection = get_database()
    farm = connection.execute(
        "SELECT * FROM farms WHERE user_id = ? LIMIT 1",
        (current_user_id(),),
    ).fetchone()

    if farm is None or farm["market_area_id"] is None:
        return render_template("market_insights.html", insights=None, market_area=None)

    market_area = connection.execute(
        "SELECT * FROM market_areas WHERE market_area_id = ?",
        (farm["market_area_id"],),
    ).fetchone()

    insights = get_market_insights(farm["market_area_id"])
    return render_template("market_insights.html", insights=insights, market_area=market_area)


@app.route("/api/weather")
@login_required
def api_weather():
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    if not lat or not lon:
        return {"error": "missing coordinates"}, 400

    weather = get_weather(lat, lon)
    if weather is None:
        return {"error": "weather unavailable"}, 500

    return weather


# ---------- Farm routes ----------
@app.route("/add-farm", methods=["GET", "POST"])
@login_required
def add_farm():
    connection = get_database()

    if request.method == "POST":
        try:
            data = form_data("farm_name", "location", "area", "market_area_id", optional=["latitude", "longitude"])
            area = require_float(data["area"], "area")
            if area <= 0:
                raise ValueError("Area must be greater than zero.")
            market_area_id = parse_optional_int(data["market_area_id"])
            if market_area_id is not None:
                area_row = connection.execute(
                    "SELECT 1 FROM market_areas WHERE market_area_id = ?",
                    (market_area_id,),
                ).fetchone()
                if area_row is None:
                    raise ValueError("Invalid market area selected.")
            latitude = require_float(data["latitude"], "latitude") if data["latitude"] else None
            longitude = require_float(data["longitude"], "longitude") if data["longitude"] else None
            if latitude is not None and not (-90 <= latitude <= 90):
                raise ValueError("Latitude must be between -90 and 90.")
            if longitude is not None and not (-180 <= longitude <= 180):
                raise ValueError("Longitude must be between -180 and 180.")
        except ValueError as e:
            flash(str(e))
            market_areas = connection.execute("SELECT * FROM market_areas").fetchall()
            return render_template("add_farm.html", market_areas=market_areas)

        connection.execute(
            """
            INSERT INTO farms (farm_name, location, total_area_acres, user_id, market_area_id, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["farm_name"],
                data["location"],
                area,
                current_user_id(),
                market_area_id,
                latitude if latitude is not None else None,
                longitude if longitude is not None else None,
            ),
        )
        connection.commit()
        return redirect("/")

    market_areas = connection.execute("SELECT * FROM market_areas").fetchall()
    return render_template("add_farm.html", market_areas=market_areas)


@app.route("/edit-farm/<int:farm_id>", methods=["GET", "POST"])
@login_required
def edit_farm(farm_id):
    connection = get_database()
    user_id = current_user_id()

    if request.method == "POST":
        try:
            data = form_data("farm_name", "location", "area", "market_area_id")
            area = require_float(data["area"], "area")
            if area <= 0:
                raise ValueError("Area must be greater than zero.")
            market_area_id = parse_optional_int(data["market_area_id"])
            if market_area_id is None:
                raise ValueError("Market area is required.")
            area_row = connection.execute(
                "SELECT 1 FROM market_areas WHERE market_area_id = ?",
                (market_area_id,),
            ).fetchone()
            if area_row is None:
                raise ValueError("Invalid market area selected.")
        except ValueError as e:
            flash(str(e))
            farm = connection.execute(
                "SELECT * FROM farms WHERE farm_id = ? AND user_id = ?",
                (farm_id, user_id),
            ).fetchone()
            market_areas = connection.execute("SELECT * FROM market_areas").fetchall()
            return render_template("edit_farm.html", farm=farm, market_areas=market_areas)

        connection.execute(
            """
            UPDATE farms SET
                farm_name = ?, location = ?, total_area_acres = ?, market_area_id = ?
            WHERE farm_id = ? AND user_id = ?
            """,
            (
                data["farm_name"],
                data["location"],
                area,
                market_area_id,
                farm_id,
                user_id,
            ),
        )
        connection.commit()
        return redirect("/farms")

    farm = connection.execute(
        "SELECT * FROM farms WHERE farm_id = ? AND user_id = ?",
        (farm_id, user_id),
    ).fetchone()
    market_areas = connection.execute("SELECT * FROM market_areas").fetchall()
    return render_template("edit_farm.html", farm=farm, market_areas=market_areas)


@app.route("/delete-farm/<int:farm_id>", methods=["POST"])
@login_required
def delete_farm(farm_id):
    connection = get_database()
    try:
        connection.execute(
            "DELETE FROM farms WHERE farm_id = ? AND user_id = ?",
            (farm_id, current_user_id()),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        flash("Can't delete this farm — it still has fields, crops, or other records linked to it. Delete those first.")
    return redirect("/farms")


@app.route("/farm-map/<int:farm_id>")
@login_required
def farm_map(farm_id):
    connection = get_database()
    farm = connection.execute(
        "SELECT * FROM farms WHERE farm_id = ? AND user_id = ?",
        (farm_id, current_user_id()),
    ).fetchone()
    if farm is None:
        flash("Farm not found.")
        return redirect("/farms")
    return render_template("farm_map.html", farm=farm)


# ---------- Field routes ----------
@app.route("/add-field", methods=["GET", "POST"])
@login_required
def add_field():
    connection = get_database()

    if request.method == "POST":
        try:
            data = form_data("farm_id", "field_name", "area_acres", "soil_type", optional=["notes"])
            farm_id = validate_farm_selection(data["farm_id"], current_user_id())
            area_acres = require_float(data["area_acres"], "area_acres")
            if area_acres <= 0:
                raise ValueError("Area must be greater than zero.")
        except ValueError as e:
            flash(str(e))
            farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (current_user_id(),)).fetchall()
            return render_template("field.html", farms=farms)

        connection.execute(
            """
            INSERT INTO fields (farm_id, field_name, area_acres, soil_type, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (farm_id, data["field_name"], area_acres, data["soil_type"], data["notes"] or None),
        )
        connection.commit()
        return redirect("/fields")

    farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (current_user_id(),)).fetchall()
    return render_template("field.html", farms=farms)


@app.route("/edit-field/<int:field_id>", methods=["GET", "POST"])
@login_required
def edit_field(field_id):
    connection = get_database()
    user_id = current_user_id()
    farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()

    field = connection.execute(
        """
        SELECT * FROM fields
        WHERE field_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (field_id, user_id),
    ).fetchone()

    if field is None:
        flash("Field not found.")
        return redirect("/fields")

    if request.method == "POST":
        try:
            data = form_data("farm_id", "field_name", "area_acres", "soil_type", optional=["notes"])
            farm_id = validate_farm_selection(data["farm_id"], user_id)
            area_acres = require_float(data["area_acres"], "area_acres")
            if area_acres <= 0:
                raise ValueError("Area must be greater than zero.")
        except ValueError as e:
            flash(str(e))
            return render_template("edit_field.html", field=field, farms=farms)

        connection.execute(
            """
            UPDATE fields SET
                farm_id = ?, field_name = ?, area_acres = ?, soil_type = ?, notes = ?
            WHERE field_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
            """,
            (farm_id, data["field_name"], area_acres, data["soil_type"], data["notes"] or None, field_id, user_id),
        )
        connection.commit()
        return redirect("/fields")

    return render_template("edit_field.html", field=field, farms=farms)


@app.route("/delete-field/<int:field_id>", methods=["POST"])
@login_required
def delete_field(field_id):
    connection = get_database()
    try:
        connection.execute(
            """
            DELETE FROM fields
            WHERE field_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
            """,
            (field_id, current_user_id()),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        flash("Can't delete this field — it still has crops or soil tests linked to it. Delete those first.")
    return redirect("/fields")


# ---------- Crop routes ----------
@app.route("/add-crop", methods=["GET", "POST"])
@login_required
def add_crop():
    connection = get_database()
    user_id = current_user_id()

    if request.method == "POST":
        try:
            data = form_data(
                "farm_id", "field_id", "crop_name", "variety", "planting_date",
                "expected_harvest_date", "area_acres", "status",
            )
            farm_id = validate_farm_selection(data["farm_id"], user_id)
            field_id, farm_id = validate_field_selection(data["field_id"], data["farm_id"], user_id)
            require_date(data["planting_date"], "planting_date")
            require_date(data["expected_harvest_date"], "expected_harvest_date")
            area_acres = require_float(data["area_acres"], "area_acres")
            if area_acres <= 0:
                raise ValueError("Area must be greater than zero.")
            if data["status"] not in {"growing", "harvested", "pending", "failed"}:
                raise ValueError("Invalid crop status.")
        except ValueError as e:
            flash(str(e))
            farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()
            fields = connection.execute(
                "SELECT * FROM fields WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)",
                (user_id,),
            ).fetchall()
            return render_template("add_crop.html", farms=farms, fields=fields)

        connection.execute(
            """
            INSERT INTO crops
            (farm_id, field_id, crop_name, variety, planting_date,
             expected_harvest_date, area_acres, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                farm_id,
                field_id,
                data["crop_name"],
                data["variety"],
                data["planting_date"],
                data["expected_harvest_date"],
                area_acres,
                data["status"],
            ),
        )
        create_notification(user_id, f"You planted {data['crop_name']} — expected harvest on {data['expected_harvest_date']}.")
        connection.commit()
        return redirect("/crops")

    farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()
    fields = connection.execute(
        "SELECT * FROM fields WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)",
        (user_id,),
    ).fetchall()

    farm = connection.execute("SELECT * FROM farms WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
    insights = []
    if farm and farm["market_area_id"]:
        insights = get_market_insights(farm["market_area_id"])

    return render_template("add_crop.html", farms=farms, fields=fields, insights=insights)


@app.route("/edit-crop/<int:crop_id>", methods=["GET", "POST"])
@login_required
def edit_crop(crop_id):
    connection = get_database()
    user_id = current_user_id()
    farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()
    fields = connection.execute(
        "SELECT * FROM fields WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)",
        (user_id,),
    ).fetchall()

    crop = connection.execute(
        """
        SELECT * FROM crops WHERE crop_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (crop_id, user_id),
    ).fetchone()

    if crop is None:
        flash("Crop not found.")
        return redirect("/crops")

    if request.method == "POST":
        try:
            data = form_data(
                "farm_id", "field_id", "crop_name", "variety", "planting_date",
                "expected_harvest_date", "area_acres", "status",
            )
            farm_id = validate_farm_selection(data["farm_id"], user_id)
            field_id, farm_id = validate_field_selection(data["field_id"], data["farm_id"], user_id)
            require_date(data["planting_date"], "planting_date")
            require_date(data["expected_harvest_date"], "expected_harvest_date")
            area_acres = require_float(data["area_acres"], "area_acres")
            if area_acres <= 0:
                raise ValueError("Area must be greater than zero.")
            if data["status"] not in {"growing", "harvested", "pending", "failed"}:
                raise ValueError("Invalid crop status.")
        except ValueError as e:
            flash(str(e))
            return render_template("edit_crop.html", crop=crop, farms=farms, fields=fields)

        connection.execute(
            """
            UPDATE crops SET
                farm_id = ?, field_id = ?, crop_name = ?, variety = ?,
                planting_date = ?, expected_harvest_date = ?, area_acres = ?, status = ?
            WHERE crop_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
            """,
            (
                farm_id,
                field_id,
                data["crop_name"],
                data["variety"],
                data["planting_date"],
                data["expected_harvest_date"],
                area_acres,
                data["status"],
                crop_id,
                user_id,
            ),
        )
        connection.commit()
        return redirect("/crops")

    return render_template("edit_crop.html", crop=crop, farms=farms, fields=fields)


@app.route("/delete-crop/<int:crop_id>", methods=["POST"])
@login_required
def delete_crop(crop_id):
    connection = get_database()
    try:
        connection.execute(
            """
            DELETE FROM crops
            WHERE crop_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
            """,
            (crop_id, current_user_id()),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        flash("Can't delete this crop — it still has activities or harvests linked to it. Delete those first.")
    return redirect("/crops")


# ---------- Soil test routes ----------
@app.route("/add-soil-test", methods=["GET", "POST"])
@login_required
def add_soil_test():
    connection = get_database()
    user_id = current_user_id()

    if request.method == "POST":
        try:
            data = form_data(
                "farm_id", "test_date", "soil_type", "ph", "nitrogen",
                "phosphorus", "potassium", "organic_matter", "moisture",
                optional=["notes"],
            )
            farm_id = validate_farm_selection(data["farm_id"], user_id)
            require_date(data["test_date"], "test_date")
            for field_name in ["ph", "nitrogen", "phosphorus", "potassium", "organic_matter", "moisture"]:
                require_float(data[field_name], field_name)
        except ValueError as e:
            flash(str(e))
            farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()
            return render_template("soil_test.html", farms=farms)

        connection.execute(
            """
            INSERT INTO soil_tests
            (farm_id, test_date, soil_type, ph, nitrogen, phosphorus, potassium, organic_matter, moisture, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                farm_id,
                data["test_date"],
                data["soil_type"],
                float(data["ph"]),
                float(data["nitrogen"]),
                float(data["phosphorus"]),
                float(data["potassium"]),
                float(data["organic_matter"]),
                float(data["moisture"]),
                data["notes"] or None,
            ),
        )
        connection.commit()
        return redirect("/soil")

    farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()
    return render_template("soil_test.html", farms=farms)


@app.route("/edit-soil-test/<int:test_id>", methods=["GET", "POST"])
@login_required
def edit_soil_test(test_id):
    connection = get_database()
    user_id = current_user_id()
    farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()

    test = connection.execute(
        """
        SELECT * FROM soil_tests
        WHERE test_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (test_id, user_id),
    ).fetchone()

    if test is None:
        flash("Soil test not found.")
        return redirect("/soil")

    if request.method == "POST":
        try:
            data = form_data(
                "farm_id", "test_date", "soil_type", "ph", "nitrogen",
                "phosphorus", "potassium", "organic_matter", "moisture",
                optional=["notes"],
            )
            farm_id = validate_farm_selection(data["farm_id"], user_id)
            require_date(data["test_date"], "test_date")
            for field_name in ["ph", "nitrogen", "phosphorus", "potassium", "organic_matter", "moisture"]:
                require_float(data[field_name], field_name)
        except ValueError as e:
            flash(str(e))
            return render_template("edit_soil_test.html", test=test, farms=farms)

        connection.execute(
            """
            UPDATE soil_tests SET
                farm_id = ?, test_date = ?, soil_type = ?, ph = ?, nitrogen = ?,
                phosphorus = ?, potassium = ?, organic_matter = ?, moisture = ?, notes = ?
            WHERE test_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
            """,
            (
                farm_id,
                data["test_date"],
                data["soil_type"],
                float(data["ph"]),
                float(data["nitrogen"]),
                float(data["phosphorus"]),
                float(data["potassium"]),
                float(data["organic_matter"]),
                float(data["moisture"]),
                data["notes"] or None,
                test_id,
                user_id,
            ),
        )
        connection.commit()
        return redirect("/soil")

    return render_template("edit_soil_test.html", test=test, farms=farms)


@app.route("/delete-soil-test/<int:test_id>", methods=["POST"])
@login_required
def delete_soil_test(test_id):
    connection = get_database()
    connection.execute(
        """
        DELETE FROM soil_tests
        WHERE test_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (test_id, current_user_id()),
    )
    connection.commit()
    return redirect("/soil")


# ---------- Activity routes ----------
@app.route("/add-activity", methods=["GET", "POST"])
@login_required
def add_activity():
    connection = get_database()
    user_id = current_user_id()

    if request.method == "POST":
        try:
            data = form_data("farm_id", "activity_date", "activity_type", "crop_id", optional=["input_used", "quantity", "notes"])
            farm_id = validate_farm_selection(data["farm_id"], user_id)
            crop_id, farm_id = validate_crop_selection(data["crop_id"], data["farm_id"], user_id)
            require_date(data["activity_date"], "activity_date")
            if data["activity_type"] not in {"Fertilizer application", "Weeding", "Irrigation", "Pest control", "Planting", "Other"}:
                raise ValueError("Invalid activity type.")
        except ValueError as e:
            flash(str(e))
            farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()
            crops = connection.execute(
                """
                SELECT c.*, f.field_name FROM crops c
                LEFT JOIN fields f ON c.field_id = f.field_id
                WHERE c.farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
                """,
                (user_id,),
            ).fetchall()
            return render_template("activity.html", farms=farms, crops=crops)

        crop = connection.execute(
            "SELECT crop_name FROM crops WHERE crop_id = ?",
            (crop_id,),
        ).fetchone()
        crop_name = crop["crop_name"] if crop else ""

        connection.execute(
            """
            INSERT INTO activities
            (farm_id, crop_id, activity_date, activity_type, crop_name, input_used, quantity, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                farm_id,
                crop_id,
                data["activity_date"],
                data["activity_type"],
                crop_name,
                data["input_used"] or None,
                data["quantity"] or None,
                data["notes"] or None,
            ),
        )
        connection.commit()
        return redirect("/activities")

    farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()
    crops = connection.execute(
        """
        SELECT c.*, f.field_name FROM crops c
        LEFT JOIN fields f ON c.field_id = f.field_id
        WHERE c.farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (user_id,),
    ).fetchall()
    return render_template("activity.html", farms=farms, crops=crops)


@app.route("/edit-activity/<int:activity_id>", methods=["GET", "POST"])
@login_required
def edit_activity(activity_id):
    connection = get_database()
    user_id = current_user_id()
    farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()

    activity = connection.execute(
        """
        SELECT * FROM activities WHERE activity_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (activity_id, user_id),
    ).fetchone()

    if activity is None:
        flash("Activity not found.")
        return redirect("/activities")

    if request.method == "POST":
        try:
            data = form_data(
                "farm_id", "activity_date", "activity_type", "crop_id",
                optional=["input_used", "quantity", "notes"],
            )
            farm_id = validate_farm_selection(data["farm_id"], user_id)
            crop_id, farm_id = validate_crop_selection(data["crop_id"], data["farm_id"], user_id)
            require_date(data["activity_date"], "activity_date")
            if data["activity_type"] not in {"Fertilizer application", "Weeding", "Irrigation", "Pest control", "Planting", "Other"}:
                raise ValueError("Invalid activity type.")
        except ValueError as e:
            flash(str(e))
            return render_template("edit_activity.html", activity=activity, farms=farms)

        crop = connection.execute(
            "SELECT crop_name FROM crops WHERE crop_id = ?",
            (crop_id,),
        ).fetchone()
        crop_name = crop["crop_name"] if crop else ""

        connection.execute(
            """
            UPDATE activities SET
                farm_id = ?, crop_id = ?, activity_date = ?, activity_type = ?, crop_name = ?,
                input_used = ?, quantity = ?, notes = ?
            WHERE activity_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
            """,
            (
                farm_id,
                crop_id,
                data["activity_date"],
                data["activity_type"],
                crop_name,
                data["input_used"] or None,
                data["quantity"] or None,
                data["notes"] or None,
                activity_id,
                user_id,
            ),
        )
        connection.commit()
        return redirect("/activities")

    return render_template("edit_activity.html", activity=activity, farms=farms)


@app.route("/delete-activity/<int:activity_id>", methods=["POST"])
@login_required
def delete_activity(activity_id):
    connection = get_database()
    connection.execute(
        """
        DELETE FROM activities
        WHERE activity_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (activity_id, current_user_id()),
    )
    connection.commit()
    return redirect("/activities")


# ---------- Harvest routes ----------
@app.route("/add-harvest", methods=["GET", "POST"])
@login_required
def add_harvest():
    connection = get_database()
    user_id = current_user_id()

    if request.method == "POST":
        try:
            data = form_data("farm_id", "crop_name", "harvest_date", "quantity", "unit", "quality", optional=["notes"])
            farm_id = validate_farm_selection(data["farm_id"], user_id)
            require_date(data["harvest_date"], "harvest_date")
            quantity = require_float(data["quantity"], "quantity")
            if quantity <= 0:
                raise ValueError("Quantity must be greater than zero.")
            if data["quality"] not in {"Excellent", "Good", "Fair", "Poor"}:
                raise ValueError("Invalid quality.")
        except ValueError as e:
            flash(str(e))
            farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()
            return render_template("harvest.html", farms=farms)

        connection.execute(
            """
            INSERT INTO harvests (farm_id, crop_name, harvest_date, quantity, unit, quality, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (farm_id, data["crop_name"], data["harvest_date"], quantity, data["unit"], data["quality"], data["notes"] or None),
        )
        connection.commit()
        create_notification(user_id, f"Harvest recorded: {data['quantity']} {data['unit']} of {data['crop_name']}.")
        return redirect("/harvests")

    farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()
    return render_template("harvest.html", farms=farms)


@app.route("/edit-harvest/<int:harvest_id>", methods=["GET", "POST"])
@login_required
def edit_harvest(harvest_id):
    connection = get_database()
    user_id = current_user_id()
    farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()

    harvest = connection.execute(
        """
        SELECT * FROM harvests WHERE harvest_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (harvest_id, user_id),
    ).fetchone()

    if harvest is None:
        flash("Harvest not found.")
        return redirect("/harvests")

    if request.method == "POST":
        try:
            data = form_data("farm_id", "crop_name", "harvest_date", "quantity", "unit", "quality", optional=["notes"])
            farm_id = validate_farm_selection(data["farm_id"], user_id)
            require_date(data["harvest_date"], "harvest_date")
            quantity = require_float(data["quantity"], "quantity")
            if quantity <= 0:
                raise ValueError("Quantity must be greater than zero.")
            if data["quality"] not in {"Excellent", "Good", "Fair", "Poor"}:
                raise ValueError("Invalid quality.")
        except ValueError as e:
            flash(str(e))
            return render_template("edit_harvest.html", harvest=harvest, farms=farms)

        connection.execute(
            """
            UPDATE harvests SET
                farm_id = ?, crop_name = ?, harvest_date = ?, quantity = ?,
                unit = ?, quality = ?, notes = ?
            WHERE harvest_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
            """,
            (farm_id, data["crop_name"], data["harvest_date"], quantity, data["unit"], data["quality"], data["notes"] or None, harvest_id, user_id),
        )
        connection.commit()
        return redirect("/harvests")

    return render_template("edit_harvest.html", harvest=harvest, farms=farms)


@app.route("/delete-harvest/<int:harvest_id>", methods=["POST"])
@login_required
def delete_harvest(harvest_id):
    connection = get_database()
    try:
        connection.execute(
            """
            DELETE FROM harvests
            WHERE harvest_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
            """,
            (harvest_id, current_user_id()),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        flash("Can't delete this harvest — it's linked to a product record. Delete that first.")
    return redirect("/harvests")


# ---------- Product routes ----------
@app.route("/add-product", methods=["GET", "POST"])
@login_required
def add_product():
    connection = get_database()
    user_id = current_user_id()

    if request.method == "POST":
        try:
            data = form_data("farm_id", "crop_name", "harvest_id", "batch_number", "product_date", "quantity", "unit", "destination", optional=["notes"])
            farm_id = validate_farm_selection(data["farm_id"], user_id)
            harvest_id, farm_id = validate_harvest_selection(data["harvest_id"], data["farm_id"], user_id)
            require_date(data["product_date"], "product_date")
            quantity = require_float(data["quantity"], "quantity")
            if quantity <= 0:
                raise ValueError("Quantity must be greater than zero.")
        except ValueError as e:
            flash(str(e))
            farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()
            harvests = connection.execute(
                "SELECT * FROM harvests WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?) ORDER BY harvest_date DESC",
                (user_id,),
            ).fetchall()
            return render_template("product.html", farms=farms, harvests=harvests)

        connection.execute(
            """
            INSERT INTO product_history
            (farm_id, crop_name, harvest_id, batch_number, product_date, quantity, unit, destination, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (farm_id, data["crop_name"], harvest_id, data["batch_number"], data["product_date"], quantity, data["unit"], data["destination"], data["notes"] or None),
        )
        connection.commit()
        return redirect("/products")

    farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()
    harvests = connection.execute(
        "SELECT * FROM harvests WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?) ORDER BY harvest_date DESC",
        (user_id,),
    ).fetchall()
    return render_template("product.html", farms=farms, harvests=harvests)


@app.route("/edit-product/<int:product_id>", methods=["GET", "POST"])
@login_required
def edit_product(product_id):
    connection = get_database()
    user_id = current_user_id()
    farms = connection.execute("SELECT * FROM farms WHERE user_id = ?", (user_id,)).fetchall()
    harvests = connection.execute(
        "SELECT * FROM harvests WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?) ORDER BY harvest_date DESC",
        (user_id,),
    ).fetchall()

    product = connection.execute(
        """
        SELECT * FROM product_history WHERE product_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (product_id, user_id),
    ).fetchone()

    if product is None:
        flash("Product record not found.")
        return redirect("/products")

    if request.method == "POST":
        try:
            data = form_data("farm_id", "crop_name", "harvest_id", "batch_number", "product_date", "quantity", "unit", "destination", optional=["notes"])
            farm_id = validate_farm_selection(data["farm_id"], user_id)
            harvest_id, farm_id = validate_harvest_selection(data["harvest_id"], data["farm_id"], user_id)
            require_date(data["product_date"], "product_date")
            quantity = require_float(data["quantity"], "quantity")
            if quantity <= 0:
                raise ValueError("Quantity must be greater than zero.")
        except ValueError as e:
            flash(str(e))
            return render_template("edit_product.html", product=product, farms=farms, harvests=harvests)

        connection.execute(
            """
            UPDATE product_history SET
                farm_id = ?, crop_name = ?, harvest_id = ?, batch_number = ?,
                product_date = ?, quantity = ?, unit = ?, destination = ?, notes = ?
            WHERE product_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
            """,
            (
                farm_id,
                data["crop_name"],
                harvest_id,
                data["batch_number"],
                data["product_date"],
                quantity,
                data["unit"],
                data["destination"],
                data["notes"] or None,
                product_id,
                user_id,
            ),
        )
        connection.commit()
        return redirect("/products")

    return render_template("edit_product.html", product=product, farms=farms, harvests=harvests)


@app.route("/delete-product/<int:product_id>", methods=["POST"])
@login_required
def delete_product(product_id):
    connection = get_database()
    connection.execute(
        """
        DELETE FROM product_history
        WHERE product_id = ? AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        """,
        (product_id, current_user_id()),
    )
    connection.commit()
    return redirect("/products")


# ---------- Listing routes ----------
@app.route("/farms")
@login_required
def farms():
    connection = get_database()
    farms = connection.execute(
        "SELECT * FROM farms WHERE user_id = ?",
        (current_user_id(),),
    ).fetchall()
    return render_template("farms.html", farms=farms)


@app.route("/fields")
@login_required
def fields():
    connection = get_database()
    fields = connection.execute(
        """
        SELECT f.*, fa.farm_name
        FROM fields f
        LEFT JOIN farms fa ON f.farm_id = fa.farm_id
        WHERE f.farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        ORDER BY f.field_id DESC
        """,
        (current_user_id(),),
    ).fetchall()
    return render_template("fields.html", fields=fields)


@app.route("/crops")
@login_required
def crops():
    connection = get_database()
    crops = connection.execute(
        """
        SELECT c.*, f.field_name
        FROM crops c
        LEFT JOIN fields f ON c.field_id = f.field_id
        WHERE c.farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        ORDER BY c.planting_date DESC
        """,
        (current_user_id(),),
    ).fetchall()
    return render_template("crops.html", crops=crops)


@app.route("/soil")
@login_required
def soil():
    connection = get_database()
    soil_tests = connection.execute(
        """
        SELECT * FROM soil_tests
        WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        ORDER BY test_date DESC
        """,
        (current_user_id(),),
    ).fetchall()
    return render_template("soil_tests.html", soil_tests=soil_tests)


@app.route("/activities")
@login_required
def activities():
    connection = get_database()
    activities = connection.execute(
        """
        SELECT * FROM activities
        WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        ORDER BY activity_date DESC
        """,
        (current_user_id(),),
    ).fetchall()
    return render_template("activities.html", activities=activities)


@app.route("/harvests")
@login_required
def harvests():
    connection = get_database()
    harvests = connection.execute(
        """
        SELECT * FROM harvests
        WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        ORDER BY harvest_date DESC
        """,
        (current_user_id(),),
    ).fetchall()
    return render_template("harvests.html", harvests=harvests)


@app.route("/products")
@login_required
def products():
    connection = get_database()
    products = connection.execute(
        """
        SELECT * FROM product_history
        WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        ORDER BY product_date DESC
        """,
        (current_user_id(),),
    ).fetchall()
    return render_template("products.html", products=products)


@app.route("/profile")
@login_required
def profile():
    connection = get_database()
    user = connection.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (current_user_id(),),
    ).fetchone()
    farm_count = connection.execute(
        "SELECT COUNT(*) FROM farms WHERE user_id = ?",
        (current_user_id(),),
    ).fetchone()[0]
    return render_template("profile.html", user=user, farm_count=farm_count)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    connection = get_database()
    user_id = current_user_id()

    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "notifications":
            weather_alerts_enabled = 1 if request.form.get("weather_alerts_enabled") else 0
            connection.execute(
                "UPDATE users SET weather_alerts_enabled = ? WHERE user_id = ?",
                (weather_alerts_enabled, user_id),
            )
            connection.commit()
            flash("Notification settings updated.")

        elif form_type == "password":
            current_password = request.form.get("current_password")
            new_password = request.form.get("new_password")
            confirm_password = request.form.get("confirm_password")

            user = connection.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            if not check_password_hash(user["password_hash"], current_password):
                flash("Current password is incorrect.")
            elif new_password != confirm_password:
                flash("New passwords do not match.")
            elif len(new_password) < 6:
                flash("New password must be at least 6 characters.")
            else:
                new_hash = generate_password_hash(new_password)
                connection.execute(
                    "UPDATE users SET password_hash = ? WHERE user_id = ?",
                    (new_hash, user_id),
                )
                connection.commit()
                flash("Password updated successfully.")

        elif form_type == "preferences":
            default_farm_id = request.form.get("default_farm_id") or None
            default_market_area_id = request.form.get("default_market_area_id") or None
            unit_system = request.form.get("unit_system")

            if default_farm_id is not None:
                try:
                    default_farm_id = int(default_farm_id)
                    if not user_owns_farm(user_id, default_farm_id):
                        raise ValueError("Invalid default farm selected.")
                except ValueError:
                    flash("Invalid default farm selected.")
                    return redirect("/settings")

            if default_market_area_id is not None:
                try:
                    default_market_area_id = int(default_market_area_id)
                    row = connection.execute(
                        "SELECT 1 FROM market_areas WHERE market_area_id = ?",
                        (default_market_area_id,),
                    ).fetchone()
                    if row is None:
                        raise ValueError("Invalid market area selected.")
                except ValueError:
                    flash("Invalid market area selected.")
                    return redirect("/settings")

            if unit_system not in {"metric", "imperial"}:
                flash("Invalid unit system selected.")
                return redirect("/settings")

            connection.execute(
                "UPDATE users SET default_farm_id = ?, default_market_area_id = ?, unit_system = ? WHERE user_id = ?",
                (default_farm_id, default_market_area_id, unit_system, user_id),
            )
            connection.commit()
            flash("Preferences updated.")

        return redirect("/settings")

    user = connection.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    farms = connection.execute(
        "SELECT * FROM farms WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    market_areas = connection.execute("SELECT * FROM market_areas").fetchall()

    return render_template("settings.html", user=user, farms=farms, market_areas=market_areas)


@app.route("/help")
@login_required
def help_page():
    return render_template("help.html")


@app.route("/about")
@login_required
def about():
    return render_template("about.html")


@app.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    if request.method == "POST":
        flash("Thanks for your feedback! We've received your message.")
        return redirect("/feedback")
    return render_template("feedback.html")


@app.route("/terms")
@login_required
def terms():
    return render_template("terms.html")


@app.route("/switch-farm")
@login_required
def switch_farm():
    connection = get_database()
    farms = connection.execute(
        "SELECT * FROM farms WHERE user_id = ?",
        (current_user_id(),),
    ).fetchall()
    return render_template("switch_farm.html", farms=farms)


@app.route("/reports")
@login_required
def reports():
    connection = get_database()
    user_id = current_user_id()

    total_farms = connection.execute(
        "SELECT COUNT(*) FROM farms WHERE user_id = ?",
        (user_id,),
    ).fetchone()[0]
    total_fields = connection.execute(
        "SELECT COUNT(*) FROM fields WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)",
        (user_id,),
    ).fetchone()[0]
    active_crops = connection.execute(
        "SELECT COUNT(*) FROM crops WHERE status = 'growing' AND farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)",
        (user_id,),
    ).fetchone()[0]
    total_harvests = connection.execute(
        "SELECT COUNT(*) FROM harvests WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)",
        (user_id,),
    ).fetchone()[0]
    total_soil_tests = connection.execute(
        "SELECT COUNT(*) FROM soil_tests WHERE farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)",
        (user_id,),
    ).fetchone()[0]

    recent_harvests = connection.execute(
        """
        SELECT h.crop_name, h.quantity, h.unit, h.harvest_date, f.farm_name
        FROM harvests h
        LEFT JOIN farms f ON h.farm_id = f.farm_id
        WHERE h.farm_id IN (SELECT farm_id FROM farms WHERE user_id = ?)
        ORDER BY h.harvest_date DESC
        LIMIT 5
        """,
        (user_id,),
    ).fetchall()

    return render_template(
        "reports.html",
        total_farms=total_farms,
        total_fields=total_fields,
        active_crops=active_crops,
        total_harvests=total_harvests,
        total_soil_tests=total_soil_tests,
        recent_harvests=recent_harvests,
    )


if __name__ == "__main__":
    app.run(debug=False)
