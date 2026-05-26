import streamlit as st
import requests
from datetime import datetime, timedelta, date
import time

# ============================================================
# GateMate - 1 File Active Multi-Flight Tracker
# User chooses flight date + exact flight time + popup alerts
# ============================================================

st.set_page_config(
    page_title="GateMate",
    page_icon="✈️",
    layout="wide"
)

# ============================================================
# Session State
# ============================================================

if "tracked_flights" not in st.session_state:
    st.session_state.tracked_flights = []

if "flight_snapshots" not in st.session_state:
    st.session_state.flight_snapshots = {}

if "flight_alerts" not in st.session_state:
    st.session_state.flight_alerts = {}

if "flight_choices" not in st.session_state:
    st.session_state.flight_choices = {}

if "pending_flight_search" not in st.session_state:
    st.session_state.pending_flight_search = ""

if "pending_flight_date" not in st.session_state:
    st.session_state.pending_flight_date = None

if "shown_popup_alerts" not in st.session_state:
    st.session_state.shown_popup_alerts = set()

if "packing_items" not in st.session_state:
    st.session_state.packing_items = [
        {"name": "Passport / ID", "packed": False},
        {"name": "Wallet", "packed": False},
        {"name": "Phone", "packed": False},
        {"name": "Phone charger", "packed": False},
        {"name": "Headphones", "packed": False},
        {"name": "Laptop / iPad", "packed": False},
        {"name": "Medicine", "packed": False},
        {"name": "Snacks", "packed": False},
        {"name": "Travel documents", "packed": False},
    ]

if "settings" not in st.session_state:
    st.session_state.settings = {
        "api_key": "",
        "refresh_seconds": 60,
        "arrival_hours_before": 2,
        "drive_minutes": 35,
    }

# ============================================================
# Sidebar
# ============================================================

st.sidebar.title("✈️ GateMate")
st.sidebar.caption("Active Multi-Flight Tracker")

page = st.sidebar.radio(
    "Menu",
    [
        "Flight Dashboard",
        "Packing List",
        "Travel Reminders",
        "Weather",
        "Settings"
    ]
)

st.sidebar.divider()

st.sidebar.subheader("🔑 API Key")

st.session_state.settings["api_key"] = st.sidebar.text_input(
    "Aviationstack API Key",
    value=st.session_state.settings["api_key"],
    type="password"
)

st.sidebar.divider()

st.sidebar.subheader("📡 Tracking Status")

if st.session_state.tracked_flights:
    st.sidebar.success(f"Tracking {len(st.session_state.tracked_flights)} flight(s)")
    for key in st.session_state.tracked_flights:
        snapshot = st.session_state.flight_snapshots.get(key, {})
        flight_name = snapshot.get("flight") or key
        from_iata = snapshot.get("from_iata") or "?"
        to_iata = snapshot.get("to_iata") or "?"
        flight_date_label = snapshot.get("selected_flight_date") or "date unknown"
        st.sidebar.write(f"• {flight_name}: {from_iata} → {to_iata} | {flight_date_label}")
else:
    st.sidebar.info("No flights tracked yet.")

st.sidebar.divider()
st.sidebar.caption("iPhone: open in Safari → Share → Add to Home Screen")

# ============================================================
# Helper Functions
# ============================================================

def clean_flight_number(flight_number):
    return flight_number.replace(" ", "").upper().strip()


def split_flight_number(flight_number):
    cleaned = clean_flight_number(flight_number)

    airline_code = ""
    number = ""

    for char in cleaned:
        if char.isalpha():
            airline_code += char
        elif char.isdigit():
            number += char

    return airline_code, number


def safe_get(dictionary, *keys):
    value = dictionary

    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)

    return value


def parse_time(time_text):
    if not time_text:
        return None

    try:
        return datetime.fromisoformat(time_text.replace("Z", "+00:00"))
    except Exception:
        return None


def get_date_from_time(time_text):
    dt = parse_time(time_text)

    if not dt:
        return None

    return dt.date()


def format_time(time_text):
    dt = parse_time(time_text)

    if not dt:
        return "Not available"

    return dt.strftime("%b %d, %Y at %I:%M %p")


def simple_time_label(time_text):
    dt = parse_time(time_text)

    if not dt:
        return "Time unavailable"

    return dt.strftime("%b %d, %I:%M %p")


def flight_matches_selected_date(flight_data, selected_date):
    """
    Filters API results to the date chosen by the user.
    Uses departure estimated first, then departure scheduled.
    """
    if not selected_date:
        return True

    dep_estimated = safe_get(flight_data, "departure", "estimated")
    dep_scheduled = safe_get(flight_data, "departure", "scheduled")

    dep_date = get_date_from_time(dep_estimated) or get_date_from_time(dep_scheduled)

    if not dep_date:
        return False

    return dep_date == selected_date


@st.cache_data(ttl=60)
def fetch_flight_options(flight_number, selected_date_str, api_key):
    if not api_key:
        return None, "Please enter your Aviationstack API key in the sidebar."

    airline_code, number = split_flight_number(flight_number)

    if not airline_code or not number:
        return None, "Invalid flight number. Use format like AA245, UA102, DL123."

    url = "http://api.aviationstack.com/v1/flights"

    params = {
        "access_key": api_key,
        "airline_iata": airline_code,
        "flight_number": number,
    }

    # Some plans/providers support this; if ignored, we still filter locally below.
    if selected_date_str:
        params["flight_date"] = selected_date_str

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()

        data = response.json()

        if "error" in data:
            return None, str(data["error"])

        flights = data.get("data", [])

        if not flights:
            return None, "No flights found. Check the flight number, date, or try closer to departure."

        selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()

        filtered_flights = [
            flight for flight in flights
            if flight_matches_selected_date(flight, selected_date)
        ]

        if not filtered_flights:
            return None, f"No flights found for {flight_number} on {selected_date_str}."

        return filtered_flights, None

    except Exception as e:
        return None, f"API error: {e}"


def extract_snapshot(flight_data):
    return {
        "flight": safe_get(flight_data, "flight", "iata"),
        "airline": safe_get(flight_data, "airline", "name"),
        "status": flight_data.get("flight_status"),

        "from_airport": safe_get(flight_data, "departure", "airport"),
        "from_iata": safe_get(flight_data, "departure", "iata"),
        "departure_terminal": safe_get(flight_data, "departure", "terminal"),
        "departure_gate": safe_get(flight_data, "departure", "gate"),
        "departure_delay": safe_get(flight_data, "departure", "delay"),
        "departure_scheduled": safe_get(flight_data, "departure", "scheduled"),
        "departure_estimated": safe_get(flight_data, "departure", "estimated"),
        "departure_actual": safe_get(flight_data, "departure", "actual"),

        "to_airport": safe_get(flight_data, "arrival", "airport"),
        "to_iata": safe_get(flight_data, "arrival", "iata"),
        "arrival_terminal": safe_get(flight_data, "arrival", "terminal"),
        "arrival_gate": safe_get(flight_data, "arrival", "gate"),
        "arrival_delay": safe_get(flight_data, "arrival", "delay"),
        "arrival_scheduled": safe_get(flight_data, "arrival", "scheduled"),
        "arrival_estimated": safe_get(flight_data, "arrival", "estimated"),
        "arrival_actual": safe_get(flight_data, "arrival", "actual"),

        "last_checked": datetime.now().strftime("%I:%M:%S %p")
    }


def make_flight_option_label(flight_data, index):
    flight_iata = safe_get(flight_data, "flight", "iata") or "Unknown Flight"

    dep_iata = safe_get(flight_data, "departure", "iata") or "?"
    arr_iata = safe_get(flight_data, "arrival", "iata") or "?"

    status = flight_data.get("flight_status") or "unknown"

    scheduled = safe_get(flight_data, "departure", "scheduled")
    estimated = safe_get(flight_data, "departure", "estimated")

    best_time = estimated or scheduled
    formatted_time = simple_time_label(best_time)

    terminal = safe_get(flight_data, "departure", "terminal") or "TBD"
    gate = safe_get(flight_data, "departure", "gate") or "TBD"

    return (
        f"{index + 1}. {flight_iata} | {dep_iata} → {arr_iata} | "
        f"{formatted_time} | Terminal {terminal} | Gate {gate} | {status}"
    )


def compare_snapshots(old, new):
    if not old:
        return ["✅ Flight tracking started."]

    watched_fields = {
        "status": "Flight status",
        "departure_terminal": "Departure terminal",
        "departure_gate": "Departure gate",
        "departure_delay": "Departure delay",
        "departure_estimated": "Estimated departure",
        "arrival_terminal": "Arrival terminal",
        "arrival_gate": "Arrival gate",
        "arrival_delay": "Arrival delay",
        "arrival_estimated": "Estimated arrival",
    }

    alerts = []

    for field, label in watched_fields.items():
        old_value = old.get(field)
        new_value = new.get(field)

        if old_value != new_value:
            alerts.append(
                f"🔔 {label} changed: {old_value or 'Not available'} → {new_value or 'Not available'}"
            )

    if not alerts:
        alerts.append("✅ No changes since last check.")

    return alerts


def add_alerts_for_flight(tracking_key, alerts):
    if tracking_key not in st.session_state.flight_alerts:
        st.session_state.flight_alerts[tracking_key] = []

    timestamp = datetime.now().strftime("%I:%M:%S %p")

    for alert in alerts:
        if "No changes" in alert:
            existing_alerts = st.session_state.flight_alerts.get(tracking_key, [])
            if existing_alerts and "No changes" in existing_alerts[0]:
                continue

        full_alert = f"{timestamp} — {alert}"

        st.session_state.flight_alerts[tracking_key].insert(0, full_alert)

        if "changed" in alert or "started" in alert:
            popup_id = f"{tracking_key}_{alert}"

            if popup_id not in st.session_state.shown_popup_alerts:
                st.toast(alert, icon="🔔")
                st.session_state.shown_popup_alerts.add(popup_id)

    st.session_state.flight_alerts[tracking_key] = st.session_state.flight_alerts[tracking_key][:20]


def show_countdown(snapshot):
    departure_time = snapshot.get("departure_estimated") or snapshot.get("departure_scheduled")
    departure_dt = parse_time(departure_time)

    if not departure_dt:
        st.warning("Departure time not available yet.")
        return

    now = datetime.now(departure_dt.tzinfo)
    time_left = departure_dt - now

    if time_left.total_seconds() <= 0:
        st.error("🚨 Departure time has passed.")
        return

    total_seconds = int(time_left.total_seconds())

    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Days", days)
    c2.metric("Hours", hours)
    c3.metric("Minutes", minutes)
    c4.metric("Seconds", seconds)


def show_leave_times(snapshot):
    departure_time = snapshot.get("departure_estimated") or snapshot.get("departure_scheduled")
    departure_dt = parse_time(departure_time)

    if not departure_dt:
        return

    airport_arrival = departure_dt - timedelta(
        hours=st.session_state.settings["arrival_hours_before"]
    )

    leave_home = airport_arrival - timedelta(
        minutes=st.session_state.settings["drive_minutes"]
    )

    st.info(f"🧳 Reach airport by: **{airport_arrival.strftime('%I:%M %p')}**")
    st.warning(f"🚗 Leave home by: **{leave_home.strftime('%I:%M %p')}**")


def status_badge(status):
    if not status:
        st.info("Status: Not available")
    elif status.lower() == "scheduled":
        st.success("Status: Scheduled")
    elif status.lower() == "active":
        st.success("Status: Active")
    elif status.lower() == "landed":
        st.info("Status: Landed")
    elif status.lower() in ["cancelled", "canceled"]:
        st.error("Status: Cancelled")
    elif status.lower() == "delayed":
        st.warning("Status: Delayed")
    else:
        st.info(f"Status: {status}")


def find_matching_selected_flight(flight_number, selected_snapshot, api_key):
    selected_date_str = selected_snapshot.get("selected_flight_date")

    flights, error = fetch_flight_options(flight_number, selected_date_str, api_key)

    if error:
        return None, error

    selected_scheduled = (
        selected_snapshot.get("selected_departure_scheduled")
        or selected_snapshot.get("departure_scheduled")
    )
    selected_from = selected_snapshot.get("from_iata")
    selected_to = selected_snapshot.get("to_iata")

    for flight in flights:
        flight_scheduled = safe_get(flight, "departure", "scheduled")
        flight_from = safe_get(flight, "departure", "iata")
        flight_to = safe_get(flight, "arrival", "iata")

        if (
            flight_scheduled == selected_scheduled
            and flight_from == selected_from
            and flight_to == selected_to
        ):
            return flight, None

    for flight in flights:
        flight_from = safe_get(flight, "departure", "iata")
        flight_to = safe_get(flight, "arrival", "iata")
        flight_scheduled = safe_get(flight, "departure", "scheduled")

        if flight_from == selected_from and flight_to == selected_to:
            if simple_time_label(flight_scheduled) == simple_time_label(selected_scheduled):
                return flight, None

    for flight in flights:
        flight_from = safe_get(flight, "departure", "iata")
        flight_to = safe_get(flight, "arrival", "iata")

        if flight_from == selected_from and flight_to == selected_to:
            return flight, None

    return None, "Could not find the selected flight on refresh. It may no longer be available from the API."


def track_one_flight(tracking_key):
    api_key = st.session_state.settings["api_key"]

    old_snapshot = st.session_state.flight_snapshots.get(tracking_key)

    if not old_snapshot:
        st.error("Missing saved flight snapshot.")
        return

    flight_number = (
        old_snapshot.get("search_flight_number")
        or old_snapshot.get("flight")
        or tracking_key
    )

    flight_data, error = find_matching_selected_flight(
        flight_number,
        old_snapshot,
        api_key
    )

    if error:
        st.error(error)
        return

    snapshot = extract_snapshot(flight_data)

    snapshot["search_flight_number"] = flight_number
    snapshot["selected_departure_scheduled"] = (
        old_snapshot.get("selected_departure_scheduled")
        or old_snapshot.get("departure_scheduled")
    )
    snapshot["selected_flight_date"] = old_snapshot.get("selected_flight_date")

    previous_snapshot = st.session_state.flight_snapshots.get(tracking_key)
    alerts = compare_snapshots(previous_snapshot, snapshot)

    st.session_state.flight_snapshots[tracking_key] = snapshot
    add_alerts_for_flight(tracking_key, alerts)

    st.subheader(f"✈️ {snapshot.get('flight') or flight_number}")

    status_badge(snapshot.get("status"))

    top1, top2, top3, top4 = st.columns(4)
    top1.metric("Airline", snapshot.get("airline") or "N/A")
    top2.metric("From", snapshot.get("from_iata") or "N/A")
    top3.metric("To", snapshot.get("to_iata") or "N/A")
    top4.metric("Last Checked", snapshot.get("last_checked"))

    st.divider()

    left, right = st.columns(2)

    with left:
        st.markdown("### Departure")
        st.write(f"**Date Selected:** {snapshot.get('selected_flight_date') or 'Not available'}")
        st.write(f"**Airport:** {snapshot.get('from_airport') or 'Not available'}")
        st.write(f"**Code:** {snapshot.get('from_iata') or 'Not available'}")
        st.write(f"**Terminal:** {snapshot.get('departure_terminal') or 'Not available'}")
        st.write(f"**Gate:** {snapshot.get('departure_gate') or 'Not available'}")
        st.write(f"**Delay:** {snapshot.get('departure_delay') or 0} min")
        st.write(f"**Scheduled:** {format_time(snapshot.get('departure_scheduled'))}")
        st.write(f"**Estimated:** {format_time(snapshot.get('departure_estimated'))}")
        st.write(f"**Actual:** {format_time(snapshot.get('departure_actual'))}")

    with right:
        st.markdown("### Arrival")
        st.write(f"**Airport:** {snapshot.get('to_airport') or 'Not available'}")
        st.write(f"**Code:** {snapshot.get('to_iata') or 'Not available'}")
        st.write(f"**Terminal:** {snapshot.get('arrival_terminal') or 'Not available'}")
        st.write(f"**Gate:** {snapshot.get('arrival_gate') or 'Not available'}")
        st.write(f"**Delay:** {snapshot.get('arrival_delay') or 0} min")
        st.write(f"**Scheduled:** {format_time(snapshot.get('arrival_scheduled'))}")
        st.write(f"**Estimated:** {format_time(snapshot.get('arrival_estimated'))}")
        st.write(f"**Actual:** {format_time(snapshot.get('arrival_actual'))}")

    st.divider()

    st.markdown("### ⏳ Active Countdown")
    show_countdown(snapshot)
    show_leave_times(snapshot)

    st.divider()

    st.markdown("### 🔔 Tracking Alerts")

    alerts_to_show = st.session_state.flight_alerts.get(tracking_key, [])[:6]

    if not alerts_to_show:
        st.info("No alerts yet.")
    else:
        for alert in alerts_to_show:
            if "changed" in alert:
                st.warning(alert)
            elif "started" in alert:
                st.success(alert)
            else:
                st.info(alert)


def remove_flight(tracking_key):
    if tracking_key in st.session_state.tracked_flights:
        st.session_state.tracked_flights.remove(tracking_key)

    if tracking_key in st.session_state.flight_snapshots:
        del st.session_state.flight_snapshots[tracking_key]

    if tracking_key in st.session_state.flight_alerts:
        del st.session_state.flight_alerts[tracking_key]


# ============================================================
# Page 1: Flight Dashboard
# ============================================================

if page == "Flight Dashboard":
    st.title("✈️ GateMate Active Flight Dashboard")
    st.write(
        "Search a flight number, choose the flight date, select the exact departure time, "
        "then actively track route, terminal, gate, delay, status, and countdown."
    )

    if not st.session_state.settings["api_key"]:
        st.warning("Enter your Aviationstack API key in the sidebar first.")

    st.divider()

    st.header("➕ Find and Choose Your Flight")

    flight_search = st.text_input(
        "Enter flight number",
        placeholder="Example: AA245, UA102, DL123"
    )

    selected_flight_date = st.date_input(
        "Choose flight date",
        value=date.today()
    )

    selected_flight_date_str = selected_flight_date.strftime("%Y-%m-%d")

    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("Search Flight Options"):
            if flight_search.strip():
                cleaned = clean_flight_number(flight_search)
                flights, error = fetch_flight_options(
                    cleaned,
                    selected_flight_date_str,
                    st.session_state.settings["api_key"]
                )

                if error:
                    st.error(error)
                else:
                    choice_key = f"{cleaned}_{selected_flight_date_str}"

                    st.session_state.flight_choices[choice_key] = flights
                    st.session_state.pending_flight_search = cleaned
                    st.session_state.pending_flight_date = selected_flight_date_str

                    st.success(
                        f"Found {len(flights)} option(s) for {cleaned} on {selected_flight_date_str}. "
                        "Choose the correct time below."
                    )
                    st.rerun()
            else:
                st.warning("Enter a flight number first.")

    with c2:
        if st.button("Refresh All Now"):
            st.cache_data.clear()
            st.rerun()

    with c3:
        if st.button("Stop All Tracking"):
            st.session_state.tracked_flights = []
            st.session_state.flight_snapshots = {}
            st.session_state.flight_alerts = {}
            st.session_state.flight_choices = {}
            st.session_state.pending_flight_search = ""
            st.session_state.pending_flight_date = None
            st.session_state.shown_popup_alerts = set()
            st.rerun()

    pending = st.session_state.pending_flight_search
    pending_date = st.session_state.pending_flight_date
    choice_key = f"{pending}_{pending_date}" if pending and pending_date else ""

    if choice_key and choice_key in st.session_state.flight_choices:
        st.divider()
        st.subheader(f"Choose exact flight for {pending} on {pending_date}")

        options = st.session_state.flight_choices[choice_key]

        option_labels = [
            make_flight_option_label(flight, i)
            for i, flight in enumerate(options)
        ]

        selected_label = st.selectbox(
            "Multiple flights may use the same flight number. Pick the correct departure time.",
            option_labels
        )

        selected_index = option_labels.index(selected_label)
        selected_flight_data = options[selected_index]

        selected_snapshot = extract_snapshot(selected_flight_data)

        st.info("Selected flight preview:")

        preview1, preview2, preview3, preview4 = st.columns(4)

        preview1.metric("Flight", selected_snapshot.get("flight") or pending)
        preview2.metric("From", selected_snapshot.get("from_iata") or "N/A")
        preview3.metric("To", selected_snapshot.get("to_iata") or "N/A")
        preview4.metric("Status", selected_snapshot.get("status") or "N/A")

        st.write(f"**Selected Date:** {pending_date}")
        st.write(
            f"**Departure:** "
            f"{format_time(selected_snapshot.get('departure_estimated') or selected_snapshot.get('departure_scheduled'))}"
        )
        st.write(
            f"**Arrival:** "
            f"{format_time(selected_snapshot.get('arrival_estimated') or selected_snapshot.get('arrival_scheduled'))}"
        )
        st.write(f"**Departure Terminal:** {selected_snapshot.get('departure_terminal') or 'Not available'}")
        st.write(f"**Departure Gate:** {selected_snapshot.get('departure_gate') or 'Not available'}")

        if st.button("Track This Exact Flight"):
            selected_scheduled = selected_snapshot.get("departure_scheduled") or str(selected_index)

            tracking_key = (
                f"{pending}_"
                f"{pending_date}_"
                f"{selected_snapshot.get('from_iata') or 'FROM'}_"
                f"{selected_snapshot.get('to_iata') or 'TO'}_"
                f"{selected_scheduled}"
            )

            if tracking_key not in st.session_state.tracked_flights:
                selected_snapshot["search_flight_number"] = pending
                selected_snapshot["selected_departure_scheduled"] = selected_snapshot.get("departure_scheduled")
                selected_snapshot["selected_flight_date"] = pending_date

                st.session_state.tracked_flights.append(tracking_key)
                st.session_state.flight_snapshots[tracking_key] = selected_snapshot
                st.session_state.flight_alerts[tracking_key] = [
                    f"{datetime.now().strftime('%I:%M:%S %p')} — ✅ Exact flight selected and tracking started."
                ]

                st.toast("✅ Exact flight selected and tracking started.", icon="✈️")

                st.success(f"Now tracking exact flight: {selected_label}")
                st.rerun()
            else:
                st.info("This exact flight is already being tracked.")

    st.divider()

    st.header("📡 Actively Tracked Flights")

    if not st.session_state.tracked_flights:
        st.info("No active flights yet. Search and select one above.")
    else:
        st.success(
            f"Tracking {len(st.session_state.tracked_flights)} flight(s). "
            f"Auto-refresh every {st.session_state.settings['refresh_seconds']} seconds."
        )

        for tracking_key in list(st.session_state.tracked_flights):
            snapshot = st.session_state.flight_snapshots.get(tracking_key, {})
            flight_title = snapshot.get("flight") or tracking_key

            with st.container(border=True):
                track_one_flight(tracking_key)

                if st.button(f"Stop Tracking {flight_title}", key=f"stop_{tracking_key}"):
                    remove_flight(tracking_key)
                    st.toast(f"Stopped tracking {flight_title}", icon="🛑")
                    st.rerun()

    st.caption(
        "Keep this page open for active tracking. Gate and terminal may not appear until closer to departure."
    )

    if st.session_state.tracked_flights:
        time.sleep(st.session_state.settings["refresh_seconds"])
        st.cache_data.clear()
        st.rerun()


# ============================================================
# Page 2: Packing List
# ============================================================

elif page == "Packing List":
    st.title("🎒 Packing List")

    total = len(st.session_state.packing_items)
    packed = sum(1 for item in st.session_state.packing_items if item["packed"])

    st.progress(packed / total if total else 0)
    st.write(f"Packed: **{packed}/{total}**")

    new_item = st.text_input("Add item", placeholder="Example: Sunglasses, book, tennis racket")

    if st.button("Add Item"):
        if new_item:
            st.session_state.packing_items.append(
                {"name": new_item, "packed": False}
            )
            st.toast(f"Added packing item: {new_item}", icon="🎒")
            st.rerun()

    st.divider()

    for i, item in enumerate(st.session_state.packing_items):
        st.session_state.packing_items[i]["packed"] = st.checkbox(
            item["name"],
            value=item["packed"],
            key=f"pack_{i}"
        )

    st.divider()

    if st.button("Reset List"):
        for item in st.session_state.packing_items:
            item["packed"] = False
        st.toast("Packing list reset.", icon="🔄")
        st.rerun()


# ============================================================
# Page 3: Travel Reminders
# ============================================================

elif page == "Travel Reminders":
    st.title("📱 Travel Reminders")
    st.write("Create reminder times for each tracked flight.")

    if not st.session_state.tracked_flights:
        st.info("Track a flight first from the Flight Dashboard.")
    else:
        flight_options = []

        for key in st.session_state.tracked_flights:
            snapshot = st.session_state.flight_snapshots.get(key, {})
            label = (
                f"{snapshot.get('flight') or key} | "
                f"{snapshot.get('from_iata') or '?'} → {snapshot.get('to_iata') or '?'} | "
                f"{snapshot.get('selected_flight_date') or 'date unknown'} | "
                f"{simple_time_label(snapshot.get('departure_scheduled'))}"
            )
            flight_options.append((label, key))

        labels = [item[0] for item in flight_options]

        selected_label = st.selectbox("Choose flight", labels)
        selected_key = dict(flight_options)[selected_label]

        snapshot = st.session_state.flight_snapshots.get(selected_key)

        if not snapshot:
            st.info("Open Flight Dashboard first so the app can fetch flight data.")
        else:
            departure_time = snapshot.get("departure_estimated") or snapshot.get("departure_scheduled")
            departure_dt = parse_time(departure_time)

            if not departure_dt:
                st.warning("Departure time not available.")
            else:
                airport_arrival = departure_dt - timedelta(
                    hours=st.session_state.settings["arrival_hours_before"]
                )

                leave_home = airport_arrival - timedelta(
                    minutes=st.session_state.settings["drive_minutes"]
                )

                reminders = [
                    ("Pack bags", leave_home - timedelta(hours=3)),
                    ("Check passport / ID", leave_home - timedelta(hours=2)),
                    ("Order Uber / Lyft", leave_home - timedelta(minutes=15)),
                    ("Leave for airport", leave_home),
                    ("Reach airport", airport_arrival),
                    ("Flight departs", departure_dt),
                ]

                for title, reminder_time in reminders:
                    with st.container(border=True):
                        st.write(f"**{title}**")
                        st.write(reminder_time.strftime("%b %d, %Y at %I:%M %p"))

                st.subheader("Copy into iPhone Reminders")

                st.code(
                    "\n".join(
                        [
                            f"{title}: {reminder_time.strftime('%b %d, %Y at %I:%M %p')}"
                            for title, reminder_time in reminders
                        ]
                    )
                )

                if st.button("Show Reminder Popup Test"):
                    st.toast("Reminder alert test: Leave for airport!", icon="📱")


# ============================================================
# Page 4: Weather
# ============================================================

elif page == "Weather":
    st.title("🌦️ Weather")
    st.write("Simple weather helper for now. You can connect a weather API later.")

    destination = st.text_input("Destination city")

    weather = st.selectbox(
        "Weather",
        ["Unknown", "Sunny", "Rainy", "Cold", "Hot", "Windy", "Snowy"]
    )

    if weather == "Rainy":
        st.info("☔ Pack an umbrella or rain jacket.")
    elif weather == "Cold":
        st.info("🧥 Pack a jacket.")
    elif weather == "Hot":
        st.info("🧢 Pack light clothes and stay hydrated.")
    elif weather == "Windy":
        st.info("🌬️ Expect possible delays or rough air.")
    elif weather == "Snowy":
        st.info("❄️ Check for delays and pack warm clothes.")
    elif weather == "Sunny":
        st.info("😎 Sunglasses may help.")
    else:
        st.info("Enter weather once you know it.")

    if st.button("Show Weather Popup Test"):
        st.toast(f"Weather reminder for {destination or 'destination'}: {weather}", icon="🌦️")


# ============================================================
# Page 5: Settings
# ============================================================

elif page == "Settings":
    st.title("⚙️ Settings")

    st.session_state.settings["refresh_seconds"] = st.number_input(
        "Refresh every how many seconds?",
        min_value=60,
        max_value=600,
        value=st.session_state.settings["refresh_seconds"]
    )

    st.session_state.settings["arrival_hours_before"] = st.number_input(
        "Reach airport how many hours before departure?",
        min_value=1,
        max_value=6,
        value=st.session_state.settings["arrival_hours_before"]
    )

    st.session_state.settings["drive_minutes"] = st.number_input(
        "Drive / Uber / Lyft time to airport in minutes",
        min_value=5,
        max_value=240,
        value=st.session_state.settings["drive_minutes"]
    )

    st.divider()

    st.subheader("Popup Alert Test")

    if st.button("Show Test Popup"):
        st.toast("🔔 This is a GateMate popup alert!", icon="✈️")

    if st.button("Clear Popup History"):
        st.session_state.shown_popup_alerts = set()
        st.toast("Popup history cleared.", icon="🧹")

    st.divider()

    st.subheader("How to use on iPhone")

    st.code("""
1. Run this app on your laptop:
   streamlit run gatemate.py

2. Open the Streamlit link on your iPhone Safari.

3. Tap Share.

4. Tap Add to Home Screen.

5. Keep the Flight Dashboard open for active tracking.
""")

    st.warning(
        "Streamlit popup alerts work inside the app while it is open. "
        "They are not iPhone lock-screen notifications."
    )