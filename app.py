"""
FoodieSafe - Flask application.

AI-powered food-demand prediction for small canteens, hostel messes and
school/college canteens.

Frontend : HTML + CSS only (Jinja templates, normal HTML forms - no JavaScript)
Backend  : Python + Flask
Database : SQLite
ML       : scikit-learn (see ml/demand_model.py)
"""

import io
import os
import sqlite3
from datetime import date, datetime, timedelta

import matplotlib

matplotlib.use("Agg")  # headless rendering, no display required
import matplotlib.pyplot as plt  # noqa: E402
from flask import (  # noqa: E402
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from database import database as db  # noqa: E402
from ml import demand_model  # noqa: E402

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FOODIESAFE_SECRET", "foodiesafe-dev-key")
app.teardown_appcontext(db.close_db)

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _parse_date(value, field="date"):
    """Return a date object or None. Accepts YYYY-MM-DD only."""
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def _parse_qty(value, field):
    """Return a non-negative int, or raise ValueError with a friendly text."""
    if value is None or str(value).strip() == "":
        return 0
    try:
        number = int(str(value).strip())
    except ValueError:
        raise ValueError(f"{field} must be a whole number.")
    if number < 0:
        raise ValueError(f"{field} cannot be negative.")
    return number


def _totals(rows):
    prepared = sum(r["prepared"] for r in rows)
    sold = sum(r["sold"] for r in rows)
    wasted = sum(r["wasted"] for r in rows)
    remaining = prepared - sold
    waste_pct = (wasted / prepared * 100.0) if prepared else 0.0
    return {
        "prepared": prepared,
        "sold": sold,
        "wasted": wasted,
        "remaining": remaining,
        "waste_pct": round(waste_pct, 1),
    }


def _most_sold_item(conn):
    row = conn.execute(
        """SELECT f.name, SUM(r.sold) AS total
           FROM daily_records r JOIN food_items f ON f.id = r.food_item_id
           GROUP BY r.food_item_id
           ORDER BY total DESC LIMIT 1"""
    ).fetchone()
    return row


def _most_wasted_item(conn):
    row = conn.execute(
        """SELECT f.name, SUM(r.wasted) AS total
           FROM daily_records r JOIN food_items f ON f.id = r.food_item_id
           GROUP BY r.food_item_id
           HAVING total > 0
           ORDER BY total DESC LIMIT 1"""
    ).fetchone()
    return row


def _record_count(conn):
    return conn.execute("SELECT COUNT(*) AS c FROM daily_records").fetchone()["c"]


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
@app.route("/dashboard")
def dashboard():
    conn = db.get_db()
    today = date.today()
    today_str = today.isoformat()

    rows = db.get_records_for_date(conn, today_str)
    totals = _totals(rows)

    item_count = conn.execute("SELECT COUNT(*) AS c FROM food_items").fetchone()["c"]
    total_records = _record_count(conn)
    most_sold = _most_sold_item(conn)
    most_wasted = _most_wasted_item(conn)

    # A small preview of the menu, grouped by category.
    menu_preview = {}
    for item in db.get_food_items(conn):
        menu_preview.setdefault(item["category"], []).append(item)

    # Recent days that actually have records (for a quick glance).
    recent_days = conn.execute(
        """SELECT date, SUM(prepared) AS prepared, SUM(sold) AS sold,
                  SUM(wasted) AS wasted
           FROM daily_records GROUP BY date ORDER BY date DESC LIMIT 5"""
    ).fetchall()

    return render_template(
        "dashboard.html",
        today=today,
        today_str=today_str,
        totals=totals,
        has_today=bool(rows),
        item_count=item_count,
        total_records=total_records,
        most_sold=most_sold,
        most_wasted=most_wasted,
        menu_preview=menu_preview,
        recent_days=recent_days,
    )


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

@app.route("/menu")
def menu():
    conn = db.get_db()
    items = db.get_food_items(conn)
    grouped = {}
    for item in items:
        grouped.setdefault(item["category"], []).append(item)

    # Keep the four known categories in a sensible order, then anything new.
    ordered = {c: grouped[c] for c in db.CATEGORY_ORDER if c in grouped}
    for cat, vals in grouped.items():
        if cat not in ordered:
            ordered[cat] = vals

    return render_template("menu.html", grouped=ordered, total_items=len(items))


# ---------------------------------------------------------------------------
# Food items
# ---------------------------------------------------------------------------

@app.route("/food-items", methods=["GET", "POST"])
def food_items():
    conn = db.get_db()

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        category = (request.form.get("category") or "").strip()
        price_raw = (request.form.get("price") or "").strip()

        errors = []
        if not name:
            errors.append("Food name is required.")
        if not category:
            errors.append("Category is required.")
        try:
            price = float(price_raw) if price_raw else -1
        except ValueError:
            price = -1
        if price < 0:
            errors.append("Price must be a number that is zero or more.")

        if not errors:
            existing = conn.execute(
                "SELECT id FROM food_items WHERE LOWER(name) = LOWER(?)", (name,)
            ).fetchone()
            if existing:
                errors.append(f'"{name}" already exists in the food items list.')

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            conn.execute(
                "INSERT INTO food_items (name, category, price) VALUES (?, ?, ?)",
                (name, category, price),
            )
            conn.commit()
            flash(f'"{name}" was added to the food items list.', "success")
        return redirect(url_for("food_items"))

    items = db.get_food_items(conn)
    known_categories = list(db.CATEGORY_ORDER)
    for row in conn.execute(
        "SELECT DISTINCT category FROM food_items ORDER BY category"
    ).fetchall():
        if row["category"] not in known_categories:
            known_categories.append(row["category"])

    return render_template(
        "food_items.html", items=items, categories=known_categories
    )


@app.route("/food-items/<int:item_id>/edit", methods=["GET", "POST"])
def edit_food_item(item_id):
    conn = db.get_db()
    item = db.get_food_item(conn, item_id)
    if item is None:
        flash("That food item was not found.", "error")
        return redirect(url_for("food_items"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        category = (request.form.get("category") or "").strip()
        price_raw = (request.form.get("price") or "").strip()

        errors = []
        if not name:
            errors.append("Food name is required.")
        if not category:
            errors.append("Category is required.")
        try:
            price = float(price_raw) if price_raw else -1
        except ValueError:
            price = -1
        if price < 0:
            errors.append("Price must be a number that is zero or more.")

        if not errors:
            clash = conn.execute(
                "SELECT id FROM food_items WHERE LOWER(name) = LOWER(?) AND id != ?",
                (name, item_id),
            ).fetchone()
            if clash:
                errors.append(f'Another food item is already named "{name}".')

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            conn.execute(
                "UPDATE food_items SET name = ?, category = ?, price = ? WHERE id = ?",
                (name, category, price, item_id),
            )
            conn.commit()
            flash(f'"{name}" was updated.', "success")
            return redirect(url_for("food_items"))

    return render_template("edit_food_item.html", item=item)


# ---------------------------------------------------------------------------
# Daily records
# ---------------------------------------------------------------------------

@app.route("/daily-records", methods=["GET", "POST"])
def daily_records():
    conn = db.get_db()
    items = db.get_food_items(conn)

    if request.method == "POST":
        record_date = _parse_date(request.form.get("date"))
        if record_date is None:
            flash("Please choose a valid date (YYYY-MM-DD).", "error")
            return redirect(url_for("daily_records", date=request.form.get("date", "")))

        saved, errors, skipped = 0, [], 0
        for item in items:
            key = str(item["id"])
            raw = {
                "prepared": request.form.get(f"prepared_{key}"),
                "sold": request.form.get(f"sold_{key}"),
                "wasted": request.form.get(f"wasted_{key}"),
            }
            # A completely blank row simply means "not recorded today".
            if all((v is None or str(v).strip() == "") for v in raw.values()):
                skipped += 1
                continue
            try:
                prepared = _parse_qty(raw["prepared"], f"{item['name']} - prepared")
                sold = _parse_qty(raw["sold"], f"{item['name']} - sold")
                wasted = _parse_qty(raw["wasted"], f"{item['name']} - wasted")
            except ValueError as exc:
                errors.append(str(exc))
                continue

            if sold > prepared:
                errors.append(
                    f"{item['name']}: sold quantity cannot be more than prepared "
                    f"({sold} > {prepared})."
                )
                continue
            remaining = prepared - sold
            if wasted > remaining:
                errors.append(
                    f"{item['name']}: wasted quantity cannot be more than the "
                    f"remaining quantity (prepared − sold = {remaining})."
                )
                continue

            conn.execute(
                """INSERT INTO daily_records (date, food_item_id, prepared, sold, wasted)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (date, food_item_id)
                   DO UPDATE SET prepared = excluded.prepared,
                                 sold = excluded.sold,
                                 wasted = excluded.wasted""",
                (record_date.isoformat(), item["id"], prepared, sold, wasted),
            )
            saved += 1

        if errors:
            for message in errors:
                flash(message, "error")
        if saved:
            conn.commit()
            flash(
                f"Saved {saved} food item record(s) for {record_date.isoformat()}.",
                "success",
            )
        elif not errors:
            flash("No quantities were entered, so nothing was saved.", "error")
        return redirect(url_for("daily_records", date=record_date.isoformat()))

    selected = _parse_date(request.args.get("date")) or date.today()
    selected_str = selected.isoformat()

    existing = {r["food_item_id"]: r for r in db.get_records_for_date(conn, selected_str)}
    day_totals = _totals(db.get_records_for_date(conn, selected_str))

    recent = conn.execute(
        """SELECT r.id, r.date, r.prepared, r.sold, r.wasted, f.name
           FROM daily_records r JOIN food_items f ON f.id = r.food_item_id
           ORDER BY r.date DESC, f.name LIMIT 30"""
    ).fetchall()

    return render_template(
        "daily_records.html",
        items=items,
        selected=selected_str,
        existing=existing,
        day_totals=day_totals,
        recent=recent,
    )


@app.route("/daily-records/<int:record_id>/delete", methods=["POST"])
def delete_daily_record(record_id):
    conn = db.get_db()
    row = conn.execute(
        "SELECT date FROM daily_records WHERE id = ?", (record_id,)
    ).fetchone()
    if row is None:
        flash("That record was not found.", "error")
        return redirect(url_for("daily_records"))
    conn.execute("DELETE FROM daily_records WHERE id = ?", (record_id,))
    conn.commit()
    flash("Record deleted.", "success")
    return redirect(url_for("daily_records", date=row["date"]))


# ---------------------------------------------------------------------------
# Predict demand
# ---------------------------------------------------------------------------

@app.route("/predict", methods=["GET", "POST"])
def predict():
    conn = db.get_db()
    items = db.get_food_items(conn)

    default_date = date.today() + timedelta(days=1)
    prediction = None
    selected_ids = [int(i["id"]) for i in items]

    if request.method == "POST":
        target = _parse_date(request.form.get("date"))
        selected_ids = [int(v) for v in request.form.getlist("items") if v.isdigit()]

        errors = []
        if target is None:
            errors.append("Please choose a valid prediction date (YYYY-MM-DD).")
        if not selected_ids:
            errors.append("Please tick at least one available menu item.")

        valid_ids = {int(i["id"]) for i in items}
        if any(i not in valid_ids for i in selected_ids):
            errors.append("One of the selected food items is no longer available.")

        if errors:
            for message in errors:
                flash(message, "error")
            prediction = None
        else:
            try:
                prediction = demand_model.predict_demand(
                    conn, target, set(selected_ids), items
                )
                # Remember which items are on the menu for that date, and
                # store the prediction so it can be compared with actual sales.
                for row in prediction["rows"]:
                    conn.execute(
                        """INSERT INTO menu (date, food_item_id) VALUES (?, ?)
                           ON CONFLICT (date, food_item_id) DO NOTHING""",
                        (target.isoformat(), row["food_item_id"]),
                    )
                    if row["predicted"] is not None:
                        conn.execute(
                            """INSERT INTO predictions
                                   (date, food_item_id, predicted, recommended, method)
                               VALUES (?, ?, ?, ?, ?)
                               ON CONFLICT (date, food_item_id)
                               DO UPDATE SET predicted = excluded.predicted,
                                             recommended = excluded.recommended,
                                             method = excluded.method,
                                             created_at = CURRENT_TIMESTAMP""",
                            (target.isoformat(), row["food_item_id"],
                             row["predicted"], row["recommended"], row["method"]),
                        )
                conn.commit()
                prediction["date"] = target.isoformat()
            except sqlite3.Error:
                conn.rollback()
                flash("Something went wrong while saving the prediction. "
                      "Please try again.", "error")

    # Prediction vs actual comparison.
    comparison = demand_model.evaluate_predictions(conn)
    compared = [c for c in comparison if c["actual"] is not None]
    pending = [c for c in comparison if c["actual"] is None]
    avg_error = None
    if compared:
        avg_error = round(
            sum(abs(c["difference"]) for c in compared) / len(compared), 1
        )

    return render_template(
        "predict.html",
        items=items,
        default_date=default_date.isoformat(),
        prediction=prediction,
        selected_ids=selected_ids,
        compared=compared[:20],
        avg_error=avg_error,
        pending_count=len(pending),
    )


# ---------------------------------------------------------------------------
# Waste
# ---------------------------------------------------------------------------

PERIODS = {
    "daily": ("Today", 1),
    "weekly": ("Last 7 days", 7),
    "monthly": ("Last 30 days", 30),
    "all": ("All time", None),
}


def _waste_data(conn, period):
    label, days = PERIODS.get(period, PERIODS["weekly"])
    params = ()
    where = ""
    if days is not None:
        start = (date.today() - timedelta(days=days - 1)).isoformat()
        where = "WHERE r.date >= ?"
        params = (start,)

    totals = conn.execute(
        f"""SELECT COALESCE(SUM(r.prepared),0) AS prepared,
                   COALESCE(SUM(r.sold),0) AS sold,
                   COALESCE(SUM(r.wasted),0) AS wasted
            FROM daily_records r {where}""",
        params,
    ).fetchone()

    by_day = conn.execute(
        f"""SELECT r.date,
                   SUM(r.prepared) AS prepared,
                   SUM(r.sold) AS sold,
                   SUM(r.wasted) AS wasted
            FROM daily_records r {where}
            GROUP BY r.date ORDER BY r.date DESC""",
        params,
    ).fetchall()

    by_item = conn.execute(
        f"""SELECT f.name, f.category,
                   SUM(r.prepared) AS prepared,
                   SUM(r.sold) AS sold,
                   SUM(r.wasted) AS wasted
            FROM daily_records r JOIN food_items f ON f.id = r.food_item_id
            {where}
            GROUP BY r.food_item_id
            ORDER BY wasted DESC, f.name""",
        params,
    ).fetchall()

    total_prepared = totals["prepared"]
    waste_pct = (totals["wasted"] / total_prepared * 100.0) if total_prepared else 0.0
    items_with_waste = [r for r in by_item if r["wasted"] > 0]

    max_waste = max([r["wasted"] for r in by_item], default=0)

    return {
        "label": label,
        "totals": totals,
        "waste_pct": round(waste_pct, 1),
        "by_day": by_day,
        "by_item": by_item,
        "items_with_waste": items_with_waste,
        "max_waste": max_waste,
    }


@app.route("/waste")
def waste():
    conn = db.get_db()
    period = request.args.get("period", "weekly")
    if period not in PERIODS:
        period = "weekly"
    data = _waste_data(conn, period)
    return render_template("waste.html", data=data, period=period, periods=PERIODS)


@app.route("/waste/chart.png")
def waste_chart():
    """Generate the waste-by-item chart on the server with matplotlib."""
    conn = db.get_db()
    period = request.args.get("period", "weekly")
    if period not in PERIODS:
        period = "weekly"
    data = _waste_data(conn, period)

    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=110)
    names = [r["name"] for r in data["by_item"]]
    wasted = [r["wasted"] for r in data["by_item"]]

    if not names or sum(wasted) == 0:
        ax.text(0.5, 0.5, "No waste recorded for this period",
                ha="center", va="center", fontsize=12, color="#6b7280")
        ax.axis("off")
    else:
        bars = ax.bar(names, wasted, color="#2e7d32")
        ax.set_ylabel("Quantity wasted")
        ax.set_title(f"Food wasted by item - {data['label']}", color="#374151")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(axis="x", rotation=35)
        for label in ax.get_xticklabels():
            label.set_ha("right")
        for bar, value in zip(bars, wasted):
            if value > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, value,
                        str(int(value)), ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return Response(buffer.getvalue(), mimetype="image/png",
                    headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def _date_range_report(conn, start, end):
    rows = conn.execute(
        """SELECT r.date, f.name, f.category,
                  r.prepared, r.sold, r.wasted
           FROM daily_records r JOIN food_items f ON f.id = r.food_item_id
           WHERE r.date BETWEEN ? AND ?
           ORDER BY r.date, f.name""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    return rows


def _by_item_summary(rows):
    summary = {}
    for r in rows:
        entry = summary.setdefault(
            r["name"], {"name": r["name"], "category": r["category"],
                        "prepared": 0, "sold": 0, "wasted": 0}
        )
        entry["prepared"] += r["prepared"]
        entry["sold"] += r["sold"]
        entry["wasted"] += r["wasted"]
    return sorted(summary.values(), key=lambda x: x["sold"], reverse=True)


@app.route("/reports")
def reports():
    conn = db.get_db()
    today = date.today()

    # ---- Daily report ----
    daily_date = _parse_date(request.args.get("report_date")) or today
    daily_rows = db.get_records_for_date(conn, daily_date.isoformat())
    daily_totals = _totals(daily_rows)

    # ---- Weekly report (7 days ending on the chosen date) ----
    week_end = _parse_date(request.args.get("week_end")) or today
    week_start = week_end - timedelta(days=6)
    week_rows = _date_range_report(conn, week_start, week_end)
    week_totals = _totals(week_rows)
    week_items = _by_item_summary(week_rows)
    week_most_wasted = next((i for i in sorted(
        week_items, key=lambda x: x["wasted"], reverse=True) if i["wasted"] > 0), None)

    # ---- Monthly report ----
    month_raw = request.args.get("month") or today.strftime("%Y-%m")
    try:
        month_start = datetime.strptime(month_raw, "%Y-%m").date()
    except ValueError:
        month_start = today.replace(day=1)
        month_raw = month_start.strftime("%Y-%m")
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)

    month_rows = _date_range_report(conn, month_start, month_end)
    month_totals = _totals(month_rows)
    month_items = _by_item_summary(month_rows)
    month_most_demanded = month_items[0] if month_items else None
    month_least_demanded = month_items[-1] if month_items else None

    # ---- Prediction accuracy (only where actuals exist) ----
    comparison = [c for c in demand_model.evaluate_predictions(conn)
                  if c["actual"] is not None]
    avg_error = None
    if comparison:
        avg_error = round(
            sum(abs(c["difference"]) for c in comparison) / len(comparison), 1
        )

    return render_template(
        "reports.html",
        daily_date=daily_date.isoformat(),
        daily_rows=daily_rows,
        daily_totals=daily_totals,
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        week_rows=week_rows,
        week_totals=week_totals,
        week_items=week_items,
        week_most_wasted=week_most_wasted,
        month_raw=month_raw,
        month_start=month_start.isoformat(),
        month_end=month_end.isoformat(),
        month_totals=month_totals,
        month_items=month_items,
        month_most_demanded=month_most_demanded,
        month_least_demanded=month_least_demanded,
        comparison=comparison[:20],
        avg_error=avg_error,
        total_records=_record_count(conn),
    )


# ---------------------------------------------------------------------------
# About / project information
# ---------------------------------------------------------------------------

@app.route("/about")
def about():
    conn = db.get_db()
    return render_template(
        "about.html",
        item_count=conn.execute("SELECT COUNT(*) AS c FROM food_items").fetchone()["c"],
        total_records=_record_count(conn),
    )


# ---------------------------------------------------------------------------
# Error handling - never show raw stack traces to the user
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404,
                           message="That page could not be found."), 404


@app.errorhandler(500)
def server_error(_error):
    return render_template("error.html", code=500,
                           message="Something went wrong on our side. "
                                   "Please go back and try again."), 500


@app.errorhandler(sqlite3.Error)
def database_error(_error):
    return render_template("error.html", code=500,
                           message="There was a problem reading the database. "
                                   "Please try again."), 500


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

db.init_db()

if __name__ == "__main__":
    # Local development server. In production the app is served by gunicorn
    # (see wsgi.py / Procfile), which imports the ``app`` object directly.
    app.run(
        debug=os.environ.get("FOODIESAFE_DEBUG", "1") == "1",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
    )
