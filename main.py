from flask import Flask, render_template, request, redirect, url_for
from collections import Counter
import csv
import os
from datetime import datetime

app = Flask(__name__)

CSV_FILE = "golf_data.csv"
current_round = {}

# Ensure CSV exists with correct headers
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode="w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "date", "course", "tees",
            "club", "launch_direction", "shot_shape",
            "strike_quality", "mental_commitment",
            "direction", "distance"
        ])

# ---------------- ROUTES ----------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/new_round", methods=["GET", "POST"])
def new_round():
    global current_round
    if request.method == "POST":
        course = request.form["course"]
        tees = request.form["tees"]
        current_round = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "course": course,
            "tees": tees
        }
        return redirect(url_for("shots"))
    return render_template("new_round.html")

@app.route("/shots", methods=["GET", "POST"])
def shots():
    global current_round
    if not current_round:
        return redirect(url_for("new_round"))

    if request.method == "POST":
        club = request.form.get("club", "")
        launch_dir = request.form.get("launch_direction", "")
        shot_shape = request.form.get("shot_shape", "")
        impact_location = request.form.get("impact_location", "")
        strike_quality = request.form.get("strike_quality", "")
        mental_commitment = request.form.get("mental_commitment", "")
        direction = request.form.get("direction", "")
        distance = request.form.get("distance", "")

        # Save to CSV
        with open(CSV_FILE, mode="a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                current_round["date"], current_round["course"], current_round["tees"],
                club, launch_dir, shot_shape, strike_quality,
                mental_commitment, direction, distance
            ])

        return redirect(url_for("shots"))

    return render_template("shots.html")

@app.route("/exit_round", methods=["POST"])
def exit_round():
    global current_round
    current_round = {}
    return redirect(url_for("index"))

@app.route("/stats")
def stats():
    if not os.path.exists(CSV_FILE):
        return render_template("stats.html", stats={})

    with open(CSV_FILE, mode="r") as f:
        reader = csv.DictReader(f)
        data = list(reader)

    # Define club groupings
    groupings = {
        "Driver": ["Dr"],
        "Fairway Woods": ["3w", "5w"],
        "Long Irons": ["4i", "5i"],
        "Mid Irons": ["6i", "7i", "8i"],
        "Short Irons": ["9i","PW"],
        "Wedges": ["50°", "54°", "58°"],
        "All Clubs": []  # special case: include all
    }

    categories = ['launch_direction', 'shot_shape', 'strike_quality',
                  'mental_commitment', 'direction', 'distance']

    stats_by_group = {}

    for group_name, clubs in groupings.items():
        if group_name == "All Clubs":
            rows = data
        else:
            rows = [row for row in data if row['club'] in clubs]

        n = len(rows)
        if n == 0:
            stats_by_group[group_name] = {cat: ("N/A", 0) for cat in categories}
            continue

        stats_by_group[group_name] = {}
        for cat in categories:
            counts = Counter(row[cat] for row in rows if row[cat])
            most_common = counts.most_common(1)
            if most_common:
                value, count = most_common[0]
                stats_by_group[group_name][cat] = (value, round(count / n * 100, 1))
            else:
                stats_by_group[group_name][cat] = ("N/A", 0)

    return render_template("stats.html", stats=stats_by_group)


# ---------------- RUN ----------------

if __name__ == "__main__":
    # Use port 81 for Replit
    app.run(host="0.0.0.0", port=81, debug=True)
