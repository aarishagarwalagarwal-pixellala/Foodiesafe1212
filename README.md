# FoodieSafe

**FoodieSafe helps canteens prepare the right amount of food by predicting demand before preparation.**

FoodieSafe is an AI-powered food-demand prediction system for small canteens, school and
college canteens, hostel messes and similar food-service managers. It uses the manager's own
historical daily records to predict the demand for each individual food item and recommends
how much should be prepared, so less food is wasted and fewer items run out.

It supports **UN Sustainable Development Goal 12 — Responsible Consumption and Production**.

---

## Technology

| Layer      | Used                                                       |
| ---------- | ---------------------------------------------------------- |
| Frontend   | HTML + CSS only, rendered with Jinja templates (no JavaScript) |
| Backend    | Python + Flask                                              |
| Database   | SQLite                                                      |
| ML         | scikit-learn (Linear Regression + Random Forest, compared by MAE) |
| Data       | pandas, NumPy                                               |
| Charts     | matplotlib, rendered on the server as a PNG                 |

There is **no JavaScript anywhere** in the application. Every interaction is a normal HTML
form, link or button handled by a Flask route.

---

## Project structure

```
foodiesafe/
├── app.py                  # Flask app: routes, validation, all pages
├── wsgi.py                 # WSGI entry point for PythonAnywhere / gunicorn
├── Procfile                # Render / Heroku-style start command
├── render.yaml             # Render Blueprint (optional one-click deploy)
├── .python-version         # pins Python 3.11.9 for hosts that read it
├── seed_demo_data.py       # OPTIONAL: inserts sample history for demos
├── requirements.txt
├── database.db             # created automatically on first run
├── database/
│   └── database.py         # SQLite schema, connections, seeding of the 10 items
├── ml/
│   └── demand_model.py     # feature engineering + model training + prediction
├── static/
│   └── style.css           # all styling
├── templates/
│   ├── base.html           # layout, navigation, flash messages
│   ├── dashboard.html
│   ├── menu.html
│   ├── food_items.html
│   ├── edit_food_item.html
│   ├── daily_records.html
│   ├── predict.html
│   ├── waste.html
│   ├── reports.html
│   ├── about.html
│   └── error.html
└── tests/
    └── test_flow.py        # end-to-end test of the main flow (73 checks)
```

---

## Installation

Requires Python 3.9 or newer.

```bash
cd foodiesafe
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Running the application

```bash
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

The SQLite database (`database.db`) and the ten initial menu items are created automatically
the first time the application starts. No manual database setup is needed.

### Optional: demo history

To demonstrate the prediction feature without typing two weeks of records by hand:

```bash
python seed_demo_data.py            # 14 days of sample history
python seed_demo_data.py --reset    # wipe records first, then seed
```

This is clearly sample data and is **never run automatically**. Leave it out to work with
only real, manually entered records.

---

## The menu

The database is initialised with exactly these ten items:

| Food Item      | Price | Category    |
| -------------- | ----: | ----------- |
| Maggi          |   ₹40 | Main Food   |
| Chole Bhature  |   ₹60 | Main Food   |
| Matra Kulcha   |   ₹50 | Main Food   |
| Veg Roll       |   ₹50 | Rolls       |
| Egg Roll       |   ₹50 | Rolls       |
| Paneer Roll    |   ₹60 | Rolls       |
| Cold Drink     |   ₹20 | Cold Drinks |
| Big Cold Drink |   ₹40 | Cold Drinks |
| Haldiram Chips |   ₹20 | Snacks      |
| TakaTak        |   ₹20 | Snacks      |

More items can be added on the **Food Items** page. The ten original items are always kept.

---

## Pages

| Page          | Route            | What it does                                                                 |
| ------------- | ---------------- | ---------------------------------------------------------------------------- |
| Dashboard     | `/` `/dashboard` | Today's prepared / sold / remaining / wasted, item count, most sold and most wasted item, menu preview, and a **Predict Tomorrow's Demand** button |
| Menu          | `/menu`          | The ten items grouped by the four categories, with prices                    |
| Food Items    | `/food-items`    | All items stored in the database; add new items; edit existing ones          |
| Daily Records | `/daily-records` | Enter prepared / sold / wasted per item for any date; remaining is calculated automatically |
| Predict Demand| `/predict`       | Choose a date and available items, get expected demand and recommended preparation, plus the prediction-vs-actual comparison |
| Waste         | `/waste`         | Total waste, waste percentage, waste by day, waste by item, most wasted items, and a server-rendered chart (daily / weekly / monthly / all) |
| Reports       | `/reports`       | Daily, weekly and monthly reports, most/least demanded items, waste %, and prediction accuracy |
| About         | `/about`         | Purpose, method, and the SDG 12 connection                                   |

---

## How the prediction works

1. **Historical records** are read from the `daily_records` table.
2. **Feature creation** builds, for each food item: day of week, month, previous quantity
   sold, previous quantity prepared, historical average demand, recent demand trend and
   menu availability. The food item is one-hot encoded as a categorical feature.
3. **Model training**: Linear Regression and a Random Forest Regressor are both trained on a
   chronological train/test split and compared using **Mean Absolute Error (MAE)**. The
   better model is refitted on all data.
4. **Prediction**: expected demand is produced per item for the chosen date.
5. **Recommendation**: `recommended = ceil(expected demand × 1.10)`, a 10% safety margin.
6. **Comparison**: stored predictions are compared with the actual quantity sold once it is
   entered, and the average absolute difference is reported.

### Honest predictions only

FoodieSafe never fabricates predictions:

* With **enough history** (at least 20 records across at least 3 items) a real model is
  trained and the page says so, naming the model and its MAE.
* With **some history but not enough to train** it shows a clearly labelled
  *historical-average estimate*, and says explicitly that this is **not** model output.
* With **no usable history** it shows:
  *"Not enough historical data for an accurate prediction. Continue adding daily records."*
  and displays no numbers at all.

---

## Database schema

```
food_items     (id, name, category, price)
daily_records  (id, date, food_item_id, prepared, sold, wasted)
menu           (id, date, food_item_id)
predictions    (id, date, food_item_id, predicted, recommended, method, created_at)
```

`daily_records.food_item_id` and `menu.food_item_id` reference `food_items.id`.
`(date, food_item_id)` is unique in both `daily_records` and `predictions`, so re-entering a
day updates the existing record instead of duplicating it.

---

## Validation and error handling

All validation happens on the server and shows friendly messages instead of Python errors:

* empty or invalid dates
* negative quantities
* non-numeric quantities
* sold quantity greater than prepared quantity
* wasted quantity greater than the remaining quantity
* missing database records
* invalid food-item IDs
* insufficient ML training data
* model-training failures (falls back to the labelled estimate)
* unknown pages (friendly 404) and server errors (friendly 500)

No stack traces are ever shown to the user.

---

## Testing

```bash
python tests/test_flow.py
```

The test uses Flask's test client and a temporary database, so it never touches your real
data. It checks database initialisation, all ten menu items, page rendering, the absence of
JavaScript, input validation, record storage and updating, remaining calculations, model
training, prediction and storage, prediction-vs-actual comparison, waste calculations and the
server-generated chart, reports, adding a food item, friendly error pages, and the
insufficient-data behaviour.

---

## Deploying to a public URL

The project is already deployment-ready: `wsgi.py` exposes the Flask app as
`application`, `gunicorn` is in `requirements.txt`, and `Procfile` / `render.yaml`
are included.

### Option A - PythonAnywhere (recommended for persistent data, free)

PythonAnywhere's free filesystem is **persistent**, so your SQLite records survive
restarts. Your site appears at `https://<yourusername>.pythonanywhere.com`.

1. **Create a free account** at <https://www.pythonanywhere.com>.
2. Open **Consoles → Bash** and upload your code. Either clone from GitHub:
   ```bash
   git clone https://github.com/<you>/foodiesafe.git
   ```
   or upload `foodiesafe.zip` through the **Files** tab and unzip it:
   ```bash
   unzip foodiesafe.zip
   ```
   You should now have `/home/<yourusername>/foodiesafe/app.py`.
3. **Create a virtualenv and install dependencies**:
   ```bash
   mkvirtualenv --python=/usr/bin/python3.11 foodiesafe-env
   pip install -r ~/foodiesafe/requirements.txt
   ```
   (If `mkvirtualenv` is not found, use `python3.11 -m venv ~/.virtualenvs/foodiesafe-env`
   and activate it with `source ~/.virtualenvs/foodiesafe-env/bin/activate`.)
4. Go to the **Web** tab → **Add a new web app** → **Manual configuration** →
   **Python 3.11**.
5. On the same Web tab, under **Virtualenv**, enter:
   `/home/<yourusername>/.virtualenvs/foodiesafe-env`
6. Under **Code**, click the **WSGI configuration file** link and replace the
   Flask section with:
   ```python
   import sys
   path = '/home/<yourusername>/foodiesafe'
   if path not in sys.path:
       sys.path.insert(0, path)

   from app import application   # noqa
   ```
   Delete the `HELLO_WORLD` example block above it. Do **not** call `app.run()`.
7. Click **Reload** (green button) and open
   `https://<yourusername>.pythonanywhere.com`.

Optional: on the Web tab add an environment variable
`FOODIESAFE_SECRET` with a random value, so session/flash cookies are signed
with your own key.

To update later: `cd ~/foodiesafe && git pull` (or re-upload), then **Reload**.

### Option B - Render (fastest public URL, free tier has caveats)

Render gives you a public `https://<name>.onrender.com` URL straight from a Git
repository.

1. **Put the code on GitHub.** From inside the project folder:
   ```bash
   git init
   git add .
   git commit -m "FoodieSafe"
   git branch -M main
   git remote add origin https://github.com/<you>/foodiesafe.git
   git push -u origin main
   ```
2. In the **Render Dashboard** (<https://dashboard.render.com>) click
   **New → Web Service** and connect the repository.
3. Use these settings:

   | Setting | Value |
   | --- | --- |
   | Language | `Python 3` |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120` |
   | Instance Type | `Free` |

4. Add **Environment Variables**:
   * `PYTHON_VERSION` = `3.11.9`
   * `FOODIESAFE_SECRET` = any long random string
   * `FOODIESAFE_DEBUG` = `0`
5. Click **Create Web Service**. The first build takes a few minutes; when it
   finishes your app is live at `https://<name>.onrender.com`.

**Alternative:** instead of step 2–3, click **New → Blueprint** and pick the
repo — Render reads the included `render.yaml` and configures everything.

#### Two important free-tier caveats

* **Cold starts.** A free service sleeps after 15 minutes without traffic; the
  next visit takes about 60 seconds to wake up. A paid instance stays warm.
* **Data is not permanent.** The free filesystem is ephemeral, so
  `database.db` is recreated (with the ten menu items) on every restart or
  redeploy, and your entered records are lost. For a live demo this is usually
  fine. For permanent data on Render you need a paid **Starter** instance plus a
  persistent disk:
  1. Add a **Disk** named `foodiesafe-data`, mount path `/var/data`, 1 GB.
  2. Add env var `FOODIESAFE_DB` = `/var/data/database.db`.
  3. Redeploy. The app creates the folder automatically and stores SQLite on the
     disk. (If you prefer PythonAnywhere, its free filesystem is already
     persistent — no disk needed.)

### Which should I pick?

| | PythonAnywhere (free) | Render (free) |
| --- | --- | --- |
| Public URL | `username.pythonanywhere.com` | `name.onrender.com` |
| Setup effort | Medium (WSGI file) | Low (GitHub + 2 commands) |
| Data persistence | **Yes** | No (needs paid disk) |
| Cold start | No | ~60 s after 15 min idle |
| Best for | Keeping real records | Quick demo link |

For an academic demo where you enter data and come back to it, use
**PythonAnywhere**. For the fastest possible public link, use **Render**.

---

## Note on accuracy

Predictions are recommendations, not guarantees. Actual demand can change because of
attendance, events, weather, holidays and other factors. Accuracy figures shown in the
application are always computed from real entered data, never assumed.
