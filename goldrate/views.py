import requests
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from datetime import datetime, timedelta

OUNCE_TO_GRAM = 31.1034768


from django.conf import settings
from django.utils import timezone
import requests

OUNCE_TO_GRAM = 31.1034768


from django.conf import settings
from django.utils import timezone
import requests

OUNCE_TO_GRAM = 31.1034768


def fetch_live_rate():
    """
    Fetch gold rate — LIMITED TO 1 external API CALL PER DAY.
    All other calls return cached values.
    """

    state = settings.GOLD_API_STATE
    today = timezone.localdate()

    # Reset count daily
    if state["date"] != today:
        state["date"] = today
        state["count"] = 0

    # STOP: Do not call API more than once per day
    if state["count"] >= state.get("max_daily_requests", 1):
        return state["cached_price"], state["cached_timestamp"]

    # ---------------------------
    # REAL API REQUEST (only 1/day)
    # ---------------------------
    url = (
        f"{settings.METALPRICE_API_URL}"
        f"?api_key={settings.METALPRICE_API_KEY}"
        "&base=INR"
        "&currencies=XAU"
    )

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
    except Exception:
        # fallback to cached value
        return state["cached_price"], state["cached_timestamp"]

    if "rates" not in data or "INRXAU" not in data["rates"]:
        return state["cached_price"], state["cached_timestamp"]

    try:
        price_per_gram = round(data["rates"]["INRXAU"] / OUNCE_TO_GRAM, 2)
        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S")

        # Store new data in cache
        state["cached_price"] = price_per_gram
        state["cached_timestamp"] = timestamp
        state["count"] += 1   # now count = 1 → block rest of day

        return price_per_gram, timestamp

    except Exception:
        return state["cached_price"], state["cached_timestamp"]


# -----------------------------
# PAGE VIEW
# -----------------------------
def gold_rate_dashboard(request):
    price_1g, ts = fetch_live_rate()

    context = {
        "price_1g": price_1g,
        "price_8g": round(price_1g * 8, 2),
        "price_1kg": round(price_1g * 1000, 2),
        "updated": ts
    }

    return render(request, "new/gold_rate.html", context)


def api_live_rate(request):
    price_1g, ts = fetch_live_rate()
    return JsonResponse({
        "ok": True,
        "price_1g": price_1g,
        "timestamp": ts
    })


def api_history(request):
    """
    Generates smooth dummy history for 5D, 1M, 1Y, MAX.
    Creates believable gold price trend data without using external API.
    """
    import random

    range_type = request.GET.get("range", "5d")

    now = datetime.now()
    points = []

    # how many points to generate
    if range_type == "5d":
        steps = 20
    elif range_type == "1m":
        steps = 30
    elif range_type == "1y":
        steps = 50
    else:   # max
        steps = 80

    # get base live rate
    base_price, _ = fetch_live_rate()

    # create smooth random variations
    price = base_price

    for i in range(steps):
        # simulate believable ups and downs
        change = random.uniform(-5, 5)  # +- ₹5 range
        price = round(price + change, 2)

        timestamp = now - timedelta(days=(steps - i) * (1 if range_type == "5d" else 2))

        points.append({
            "t": timestamp.isoformat(),
            "v": price
        })

    return JsonResponse({"ok": True, "data": points})

