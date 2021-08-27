import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    rows = db.execute("SELECT * FROM portfolio WHERE id=:user_id", user_id=session["user_id"])
    cash = db.execute("SELECT cash FROM users where id=:cur_id", cur_id=session["user_id"])
    stock_total = db.execute("SELECT sum(TOTAL) FROM Portfolio where id=:cur_id", cur_id=session["user_id"])
    if stock_total[0]["sum(TOTAL)"] is None:
        user_total = cash[0]["cash"]
    else:
        user_total = stock_total[0]["sum(TOTAL)"] + cash[0]["cash"]

    return render_template("index.html", rows=rows, cash=cash[0]["cash"], usd=usd, TOTAL=user_total, lookup=lookup)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    current_user = session["user_id"]
    cash = db.execute("SELECT cash FROM users WHERE id=:cur_id", cur_id=session["user_id"])
    user_cash = cash[0]["cash"]

    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))
        name = stock["name"]
        price = stock["price"]
        shares = request.form.get("shares")
        total = price*int(shares)
        user_cash -= total
        if user_cash < 0:
            bought = "Insufficient"
            if (request.form['action'] == "Buy"):
                flash("Insufficient funds!")
                return redirect('/')
            else:
                return render_template("buy.html", bought=bought)
        user_share = db.execute("SELECT Shares FROM Portfolio WHERE id=:cur_id and Name=:name", cur_id=session["user_id"], name=name)
        test = db.execute("SELECT * FROM Portfolio WHERE Name=:name and id=:cur_id", name=name, cur_id=session["user_id"])
        if shares == "0":
            bought = "Zero"
            if (request.form['action'] == "Buy"):
                flash("Unable to buy zero stocks")
                return redirect('/')
            else:
                return render_template("buy.html", bought=bought)
        # check if user already owns share of stock
        elif (len(test) != 1 or price != test[0]["Price"]):
            total = price*int(shares)
            db.execute("INSERT INTO Portfolio (id, Symbol, Name, Shares, Price, TOTAL) VALUES (:user_id, :Symbol, :Name, :Shares, :price, :TOTAL)",
            user_id=current_user, Symbol=stock["symbol"], Name=name, Shares=shares, price=price,TOTAL=total)
            db.execute("INSERT INTO History (Symbol, Shares, Price, Option, id) VALUES (:symbol, :shares, :price, :option, :cur_id)", symbol=stock["symbol"], shares=request.form.get("shares"), price=price, option="buy", cur_id=session["user_id"])
        else:
            shares = int(shares) + int(user_share[0]["Shares"])
            total = price*int(shares)
            db.execute("UPDATE Portfolio SET Shares=:shares, TOTAL=:total WHERE Name=:name AND id=:user_id", shares=shares, total=total, name=name, user_id=current_user)
            db.execute("INSERT INTO History (Symbol, Shares, Price, Option, id) VALUES (:symbol, :shares, :price, :option, :cur_id)", symbol=stock["symbol"], shares=request.form.get("shares"), price=price, option="buy", cur_id=session["user_id"])

        bought = "Success"
        db.execute("UPDATE users SET cash = :user_cash WHERE id = :current_user", user_cash=user_cash, current_user=current_user)
        
        if (request.form['action'] == "Buy"):
            flash("Successfully bought")
            return redirect('/')
        else:
            return render_template("buy.html", bought=bought)
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    query = db.execute("SELECT * FROM History WHERE id=:cur_id ORDER BY Date DESC", cur_id=session["user_id"])
    return render_template("history.html", query=query, usd=usd)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    quote = request.form.get("quote")
    stock = lookup(str(quote))
    if request.method == "POST":
        return render_template("quoted.html", name=stock["name"], price=stock["price"], symbol=stock["symbol"])
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        if not request.form.get("username") and not request.form.get("password"):
            return apology("Must provide username and password", 403)
        elif not request.form.get("username"):
            return apology("Must provide username", 403)
        elif not request.form.get("password"):
            return apology("Must provide password", 403)

        user = db.execute("SELECT * FROM users WHERE username = :username", username = request.form.get("username"))
        if (len(user) == 1):
            return apology("Username already exists", 403)

        password = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256', salt_length=8)

        username=request.form.get("username")
        if check_password_hash(password, request.form.get("confirmation")):
            db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)", username=username, password=password)
            return redirect("/")
        else:
            return apology("Passwords do not match", 403)

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    stocks = db.execute("SELECT Symbol FROM Portfolio WHERE id=:user_id", user_id=session["user_id"])

    if request.method == "POST":
        amount = request.form.get("shares")
        symbol = request.form.get("symbol")

        query = db.execute("SELECT * FROM Portfolio WHERE id=:user_id AND Symbol=:symbol", user_id=session["user_id"], symbol=symbol)
        cash = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=session["user_id"])
        price = lookup(str(symbol))


        sold = int(query[0]["Shares"] - int(amount))

        total = query[0]["TOTAL"]

        if amount == "0":
            sold_ = "Zero"
            if request.form['action'] == 'Sell':
                flash("Unable to sell zero stock")
                return redirect("/")
            else:
                return render_template("sell.html", sold_=sold_)
        elif (sold > 0):
            total = total - (int(amount) * price["price"])
            cash = cash[0]["cash"] + (int(amount) * price["price"])
            db.execute("UPDATE Portfolio SET shares=:shares, TOTAL=:total WHERE id=:user_id AND Symbol=:symbol", shares=sold, total=total, user_id=session["user_id"], symbol=symbol)
            db.execute("UPDATE users SET cash=:cash WHERE id=:user_id", cash=cash, user_id=session["user_id"])
            db.execute("INSERT INTO History (Symbol, Shares, Price, Option, id) VALUES (:symbol, :shares, :price, :option, :cur_id)", symbol=symbol, shares=amount, price=price["price"], option="sell", cur_id = session["user_id"])
            sold_ = "Success"
            if request.form['action'] == 'Sell':
                flash("Succesfully sold!")
                return redirect("/") 
            else:
                return render_template("sell.html", sold_=sold_)
        elif (sold == 0):
            cash = cash[0]["cash"] + (int(amount) * query[0]["Price"])
            db.execute("DELETE FROM Portfolio WHERE id=:user_id AND Symbol=:symbol", user_id=session["user_id"], symbol=symbol)
            db.execute("UPDATE users SET cash=:cash WHERE id=:user_id", cash=cash, user_id=session["user_id"])
            db.execute("INSERT INTO History (Symbol, Shares, Price, Option, id) VALUES (:symbol, :shares, :price, :option, :cur_id)", symbol=symbol, shares=amount, price=price["price"], option="sell", cur_id = session["user_id"])
            sold_ = "Success"
            if (request.form['action'] == 'Sell'):
                flash("Successfully sold!")
                return redirect("/")
            else:
                return render_template("sell.html", sold_=sold_)
        else:
            sold_ = "Fail"
            if (request.form['action'] == 'Sell'):
                flash("You do not own enough of this stock to sell!")
                return redirect("/")
            else:
                return render_template("sell.html", stocks=stocks, sold_=sold_)

        return render_template("sell.html", stocks=stocks)
    return render_template("sell.html", stocks=stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
