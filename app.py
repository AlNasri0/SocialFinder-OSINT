from flask import Flask, render_template, request
from searchers.all_search import search_username

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def home():

    results = []
    found_count = 0
    username = ""

    if request.method == "POST":

        username = request.form["username"]

        results = search_username(username)

        found_count = sum(
            result["found"]
            for result in results
        )

    return render_template(
        "index.html",
        results=results,
        found_count=found_count,
        username=username
    )

if __name__ == "__main__":
    app.run(debug=True)