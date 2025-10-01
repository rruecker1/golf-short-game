from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from collections import Counter
import os, csv, random, io
from datetime import datetime
import pandas as pd
import dropbox
from dropbox import DropboxOAuth2FlowNoRedirect, DropboxOAuth2Flow

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Dropbox setup with refresh token
APP_KEY = os.environ.get("DROPBOX_APP_KEY")
APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN")
DBX_PATH = "/round_history.csv"  # Path inside Dropbox

if not all([APP_KEY, APP_SECRET, REFRESH_TOKEN]):
    raise ValueError("Missing Dropbox credentials. Check Render environment variables.")

dbx = dropbox.Dropbox(
    oauth2_refresh_token=REFRESH_TOKEN,
    app_key=APP_KEY,
    app_secret=APP_SECRET
)

DBX_PATH = "/round_history.csv"  # Path inside Dropbox

# Ensure history file exists in Dropbox
def ensure_history_file():
    try:
        dbx.files_get_metadata(DBX_PATH)
    except dropbox.exceptions.ApiError:
        header = "Round,Timestamp,Shot,Prompt,Proximity,Direction,Strokes\n"
        dbx.files_upload(header.encode(), DBX_PATH, mode=dropbox.files.WriteMode.overwrite)

ensure_history_file()

def load_history():
    """Download round_history.csv from Dropbox into DataFrame"""
    try:
        metadata, res = dbx.files_download(DBX_PATH)
        data = res.content.decode()
        return pd.read_csv(io.StringIO(data))
    except Exception as e:
        print(f"Error loading history: {e}")
        return pd.DataFrame()

def save_history(df):
    """Upload DataFrame back to Dropbox as CSV"""
    out = io.StringIO()
    df.to_csv(out, index=False)
    dbx.files_upload(out.getvalue().encode(), DBX_PATH, mode=dropbox.files.WriteMode.overwrite)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/new_round")
def new_round():
    categories = ["Bunker", "Short Fairway Chip", "Medium Fairway Chip",
                  "Long Fairway Chip", "Short Rough Chip", "Medium Rough Chip"]
    pins = ["Short Pin", "Middle Pin", "Long Pin"]
    prompts = [f"{c} - {p}" for c in categories for p in pins]  # 18 shots
    random.shuffle(prompts)
    session["prompts"] = prompts
    session["round_id"] = datetime.now().strftime("%Y%m%d%H%M%S")
    return redirect(url_for("shot", n=1))

@app.route("/shot/<int:n>")
def shot(n):
    prompts = session.get("prompts")
    if not prompts:
        flash("No active round. Start a new round.")
        return redirect(url_for("index"))

    if n > len(prompts):
        return redirect(url_for("stats"))

    next_prompt = prompts[n] if n < len(prompts) else None

    # Load saved shot data
    df = load_history()
    form_data = {}

    if not df.empty:
        # Ensure correct types
        df["Shot"] = df["Shot"].astype(int)
        df["Round"] = df["Round"].astype(str)

        match = df[(df["Round"] == str(session["round_id"])) & (df["Shot"] == n)]
        if not match.empty:
            form_data = {
                "direction": str(match.iloc[0]["Direction"]),
                "proximity": str(match.iloc[0]["Proximity"]),
                "strokes": str(match.iloc[0]["Strokes"])
            }

    # Build navigator with saved status
    shot_links = [{"n": i+1, "saved": False} for i in range(len(prompts))]
    if not df.empty:
        saved_shots = df[df["Round"] == str(session["round_id"])]["Shot"].astype(int).tolist()
        for s in shot_links:
            if s["n"] in saved_shots:
                s["saved"] = True

    return render_template(
        "shot.html",
        n=n,
        prompt=prompts[n-1],
        form_data=form_data,
        next_prompt=next_prompt,
        shot_links=shot_links
    )


@app.route("/save_shot/<int:n>", methods=["POST"])
def save_shot(n):
    direction = request.form.get("direction", "").strip()
    prox = request.form.get("proximity", "").strip()
    strokes = request.form.get("strokes", "").strip()

    errors = []
    if not direction:
        errors.append("Please select a direction.")
    if not prox:
        errors.append("Please select a proximity option.")
    if not strokes:
        errors.append("Please select strokes.")

    if errors:
        for e in errors:
            flash(e)
        return redirect(url_for("shot", n=n))

    # Load current history
    df = load_history()

    # Ensure correct types
    if not df.empty:
        df["Shot"] = df["Shot"].astype(int)
        df["Round"] = df["Round"].astype(str)

    # New row to insert
    row = {
        "Round": str(session["round_id"]),
        "Timestamp": datetime.now().isoformat(timespec="seconds"),
        "Shot": n,
        "Prompt": session["prompts"][n - 1],
        "Proximity": prox,
        "Direction": direction,
        "Strokes": strokes,
    }

    # Remove any existing record for this Round + Shot
    if not df.empty:
        df = df[~((df["Round"] == row["Round"]) & (df["Shot"] == n))]

    # Append the new row
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    # Save back to CSV (overwrite the file)
    save_history(df)

    if n >= len(session["prompts"]):
        return redirect(url_for("stats"))
    return redirect(url_for("shot", n=n + 1))


@app.route("/stats")
def stats():
    df = load_history()
    if df.empty:
        return render_template("stats.html", has_data=False)

    # Map proximity safely
    prox_map = {"Made": 0, "0-3": 1.5, "3-6": 4.5, "6-9": 7.5, "9-12": 10.5, "12-15": 13.5, ">15": 18}
    df["Proximity_num"] = df["Proximity"].map(lambda x: prox_map.get(x, 0))

    # Map strokes safely
    strokes_map = {"1": 1, "2": 2, "3": 3, ">3": 4}
    df["Strokes_num"] = df["Strokes"].astype(str).map(lambda x: strokes_map.get(x, 4))

    # Split Prompt into Category and Pin
    df["Category"] = df["Prompt"].apply(lambda x: x.split(" - ")[0])
    df["Pin"] = df["Prompt"].apply(lambda x: x.split(" - ")[1])

    # Overall stats
    total_shots = len(df)
    avg_prox = round(df["Proximity_num"].mean(), 2)
    updown_pct = round((df["Strokes_num"] <= 2).sum() / total_shots * 100, 1)
    holed_pct = round((df["Strokes_num"] == 1).sum() / total_shots * 100, 1)

    # Hierarchical stats: Category -> Pin
    shot_stats = {}
    for cat, group in df.groupby("Category"):
        shot_stats[cat] = {}
        for pin, pin_group in group.groupby("Pin"):
            avg_prox_pin = round(pin_group["Proximity_num"].mean(), 2)
            total_pin = len(pin_group)
            updown = round((pin_group["Strokes_num"] <= 2).sum() / total_pin * 100, 1)
            holed = round((pin_group["Strokes_num"] == 1).sum() / total_pin * 100, 1)

            # Compute most common directions
            direction_counts = Counter()
            for d in pin_group["Direction"]:
                if "long" in d: direction_counts["long"] += 1
                if "short" in d: direction_counts["short"] += 1
                if "left" in d: direction_counts["left"] += 1
                if "right" in d: direction_counts["right"] += 1
        
            if direction_counts:
                max_count = max(direction_counts.values())
                most_common_dir = [k for k, v in direction_counts.items() if v == max_count]
                most_common_dir_str = ", ".join(most_common_dir)
            else:
                most_common_dir_str = ""
        
            shot_stats[cat][pin] = {
                "avg_prox": avg_prox_pin,
                "updown_pct": updown,
                "holed_pct": holed,
                "most_common_direction": most_common_dir_str
            }
    return render_template(
        "stats.html",
        has_data=True,
        total_shots=total_shots,
        avg_prox=avg_prox,
        updown_pct=updown_pct,
        holed_pct=holed_pct,
        shot_stats=shot_stats
    )

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

