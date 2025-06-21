import upstox_client
import os
import logging
import sys
import time
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
import matplotlib.pyplot as plt
import pandas as pd
import json
import requests
import urllib3 # Import urllib3 for SSL warnings disable

# Disable insecure request warnings globally for urllib3
# ⚠️⚠️⚠️ SECURITY WARNING: This disables SSL certificate verification globally.
# Use this with EXTREME CAUTION and only if you understand the security implications.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ⚠️⚠️⚠️ EXTREMELY IMPORTANT SECURITY WARNING ⚠️⚠️⚠️
# NEVER HARDCODE API KEYS, SECRETS, OR ACCESS TOKENS IN PRODUCTION CODE.
# THIS IS FOR DEMONSTRATION/TESTING PURPOSES ONLY.
# For production, use environment variables (e.g., os.getenv("ENV_VAR_NAME"))
# or a secure configuration management system.
API_KEY = "62006138-2d61-4dc0-942c-b90e1e3e5b72"
API_SECRET = "94zecafzmm"
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiIxMDkyNTMiLCJqdGkiOiI2ODU2ZDNhY2E3OTM4ZDQ4Y2JiOTA4YzEiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc1MDUyMDc0OCwiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzUwNTQzMjAwfQ.1E7nPjsZF81SCg2KAqZVjEFRFOAUrSvWQ8hRvee29bQ"
# End of Security Warning for Credentials

# --- Telegram Bot Configuration (For Alerts) ---
# Replace with your actual Telegram Bot Token (from @BotFather, NOT the bot username)
# Example: "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJ"
TELEGRAM_BOT_TOKEN = "7570999010:AAGmr04n6NI1u-Qvplz92NOCUcy0lI3VCcA"
# Replace with your actual Telegram Chat ID (found via https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates)
TELEGRAM_CHAT_ID = "460335553"

# --- Logging Setup ---
# Create a custom logger
logger = logging.getLogger('SensexTradingBot')
logger.setLevel(logging.INFO) # Set default logging level

# Create handlers
# Console handler
c_handler = logging.StreamHandler(sys.stdout)
# File handler (rotates daily, keeps 7 days)
f_handler = TimedRotatingFileHandler("trading_bot.log", when="midnight", interval=1, backupCount=7)

# Create formatters and add it to handlers
c_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
f_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s') # More detail for file
c_handler.setFormatter(c_format)
f_handler.setFormatter(f_format)

# Add handlers to the logger
logger.addHandler(c_handler)
logger.addHandler(f_handler)

# --- Trading Parameters ---
SENSEX_FUT_SYMBOL_PATTERN = "SENSEX" # Part of the trading symbol or name
SENSEX_LOT_SIZE = 10 # Confirmed lot size for Sensex Futures and Options
DESIRED_WEEKLY_PROFIT = 75000.0
MAX_DAILY_LOSS_PERCENT = 0.02 # 2% of capital
RISK_PER_TRADE_PERCENT = 0.01 # 1% of capital per trade
RISK_REWARD_RATIO = 2.0 # Aim for 1:2 or 1:3 as desired, e.g., 2.0 or 3.0

# Flag to control actual order execution vs. dry run/alerting only
DRY_RUN_MODE = True # Set to False to enable actual trading

# Global state for positions and P&L (in a real system, consider a database for persistence)
current_positions = {} # {instrument_key: {'quantity': N, 'avg_price': M, 'side': 'BUY'/'SELL', 'stop_loss_price': SL, 'take_profit_price': TP}}
total_capital = 0.0 # Will be fetched from Upstox
daily_pnl = 0.0

# P&L History for Graphing
pnl_history_file = "pnl_history.json"
pnl_data = [] # List of {'timestamp': '...', 'pnl': X, 'capital': Y}

# --- Upstox API Client Initialization ---
# Ensure ApiException is imported correctly
from upstox_client.rest import ApiException

api_client = upstox_client.ApiClient()
api_client.configuration.access_token = ACCESS_TOKEN
# ⚠️⚠️⚠️ SECURITY WARNING: Setting verify_ssl to False DISABLES SSL CERTIFICATE VERIFICATION ⚠️⚠️⚠️
# Use this with EXTREME CAUTION. It is highly NOT recommended for production environments.
# This is a workaround for certificate issues in specific network environments (e.g., corporate proxies).
# The ideal solution is to fix your system's SSL certificate trust chain.
# Note: With urllib3.disable_warnings at the top, this might be redundant but kept for clarity.
api_client.verify_ssl = False

# Initialize specific API instances
login_api = upstox_client.LoginApi(api_client)
market_quote_api = upstox_client.MarketQuoteApi(api_client)
market_quote_v3_api = upstox_client.MarketQuoteV3Api(api_client) # For option Greeks
order_api = upstox_client.OrderApi(api_client)
portfolio_api = upstox_client.PortfolioApi(api_client)
user_api = upstox_client.UserApi(api_client)
history_api = upstox_client.HistoryApi(api_client) # For historical data
options_api = upstox_client.OptionsApi(api_client) # For option chain details

# --- Helper Functions ---

def send_alert_to_mobile(message):
    """Sends a message via Telegram bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.warning("Telegram bot not configured or placeholder token found. Cannot send mobile alerts.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown' # Optional: use Markdown for formatting
    }
    try:
        # ⚠️⚠️⚠️ SECURITY WARNING: verify=False DISABLES SSL CERTIFICATE VERIFICATION ⚠️⚠️⚠️
        # Only use this if you understand the security implications and cannot resolve
        # certificate issues in your environment. It's not recommended for production.
        response = requests.post(url, json=payload, verify=False)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        logger.info(f"Telegram alert sent: {message[:50]}...") # Log first 50 chars
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Telegram alert: {e}")
        if 'response' in locals() and hasattr(response, 'text'):
            logger.error(f"Telegram API response: {response.text}")
        # Avoid recursive alerts if the alert system itself is failing, this is already logged.

def load_pnl_history():
    """Loads P&L history from a JSON file."""
    global pnl_data
    if os.path.exists(pnl_history_file):
        try:
            with open(pnl_history_file, 'r') as f:
                pnl_data = json.load(f)
            logger.info("P&L history loaded.")
        except json.JSONDecodeError:
            logger.error("Error decoding P&L history file. Starting fresh.", exc_info=True)
            pnl_data = []
        except Exception as e:
            logger.error(f"Unexpected error loading P&L history: {e}", exc_info=True)
            pnl_data = []
    else:
        logger.info("No P&L history file found. Starting fresh.")

def save_pnl_history():
    """Saves P&L history to a JSON file."""
    try:
        with open(pnl_history_file, 'w') as f:
            json.dump(pnl_data, f, indent=4)
        logger.info("P&L history saved.")
    except Exception as e:
        logger.error(f"Error saving P&L history: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot Alert: Failed to save P&L history! {e}")

def update_pnl_history(current_pnl_val, current_capital_val):
    """Adds current P&L and capital to history and saves."""
    pnl_data.append({
        'timestamp': datetime.now().isoformat(),
        'pnl': current_pnl_val,
        'capital': current_capital_val
    })
    save_pnl_history()

def generate_pnl_graph():
    """Generates and saves a P&L graph from historical data."""
    if not pnl_data:
        logger.info("No P&L data to graph yet.")
        return

    try:
        df = pd.DataFrame(pnl_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)

        plt.figure(figsize=(14, 7))
        plt.plot(df.index, df['pnl'], label='P&L Over Time', color='blue', marker='o', markersize=2, linestyle='-')
        plt.axhline(0, color='red', linestyle='--', linewidth=0.8, label='Breakeven')

        # Add a line for the daily loss limit
        if total_capital > 0:
            daily_loss_limit_rupees = -(total_capital * MAX_DAILY_LOSS_PERCENT)
            plt.axhline(daily_loss_limit_rupees, color='orange', linestyle=':', linewidth=0.8, label=f'Daily Loss Limit ({MAX_DAILY_LOSS_PERCENT*100}%)')

        plt.title('Trading Bot P&L Trend', fontsize=16)
        plt.xlabel('Time', fontsize=12)
        plt.ylabel('P&L (INR)', fontsize=12)
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.legend(fontsize=10)
        plt.tight_layout()

        graph_filename = f"pnl_graph_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        plt.savefig(graph_filename)
        logger.info(f"P&L graph saved as {graph_filename}")
        plt.close() # Close plot to free memory
    except Exception as e:
        logger.error(f"Error generating P&L graph: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot Alert: Failed to generate P&L graph! {e}")


def get_current_capital():
    """Fetches available margin from Upstox."""
    try:
        # UserApi.get_user_fund_margin() requires 'api_version' argument.
        # Most current Upstox V2 APIs use "2.0"
        funds_data = user_api.get_user_fund_margin(segment="FUTURES", api_version="2.0")

        # Inspect the structure of funds_data.data to correctly extract available_margin
        # It might be in data.equity.available_margin or data.fno.available_margin, etc.
        available_margin = 0.0
        if hasattr(funds_data.data, 'equity') and hasattr(funds_data.data.equity, 'available_margin'):
            available_margin = funds_data.data.equity.available_margin
            logger.info(f"Fetched equity available margin: {available_margin:.2f}")
        elif hasattr(funds_data.data, 'fno') and hasattr(funds_data.data.fno, 'available_margin'):
            available_margin = funds_data.data.fno.available_margin
            logger.info(f"Fetched F&O available margin: {available_margin:.2f}")
        elif hasattr(funds_data.data, 'available_margin'): # Less common, but for aggregated view
            available_margin = funds_data.data.available_margin
            logger.info(f"Fetched top-level available margin: {available_margin:.2f}")
        else:
            logger.warning("Could not find 'available_margin' in standard fund data paths.")
            logger.debug(f"Full funds data structure: {funds_data}") # Log full structure for debugging
            send_alert_to_mobile("Bot Warning: Could not find available margin in funds data.")
            return 0.0 # Return 0 if not found, to prevent trading

        return available_margin
    except ApiException as e:
        logger.error(f"Upstox API Error while fetching funds: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot Alert: Upstox API Error on funds fetch! {e}")
        return 0.0
    except Exception as e:
        logger.critical(f"Critical unexpected error fetching funds: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot CRITICAL: Unexpected error fetching funds! {e}")
        return 0.0

def get_sensex_instrument_key(instrument_type, expiry_date_str, strike_price=None, option_type=None):
    """
    Placeholder: In a real bot, you would query the Upstox Instruments API
    (e.g., portfolio_api.get_instruments or get_option_contracts) to find the correct
    instrument_key for the current month's Sensex Futures or the relevant Option.

    Upstox instrument_keys follow specific patterns, e.g., 'BSE_FO|INDEX_FUT|SENSEX|YYYYMMDD'
    or 'BSE_FO|INDEX_OPT|SENSEX|YYYYMMDD|STRIKE|CE/PE'.
    """
    logger.warning("get_sensex_instrument_key is a placeholder. Implement robust instrument lookup using Upstox API.")

    # Dummy implementation for demonstration.
    # Replace with actual logic to fetch latest expiry and instrument key from Upstox API.
    # For testing, you might manually put a known current instrument key here.

    # As of June 21, 2025, assuming a next-week expiry for illustration
    # You MUST replace this with actual logic to find the correct, active instrument key

    if instrument_type == "FUT":
        # Example for June 2025 expiry. Check Upstox for actual format.
        # Sensex futures expiry is typically the last Monday of the expiry month from Sep 2025 as per recent changes.
        # For June 2025, it might still be Thursday or already shifted to Monday.
        # You would query Upstox's instruments API to get the correct instrumentKey.
        return "BSE_FO|INDEX_FUT|SENSEX|20250630" # Example: June 30th 2025 expiry
    elif instrument_type == "OPT":
        # Example: Sensex 83000 CE for a given expiry.
        return f"BSE_FO|INDEX_OPT|SENSEX|{expiry_date_str.replace('-', '')}|{int(strike_price)}|{option_type}"
    return None

def place_upstox_order(instrument_key, quantity, transaction_type, order_type="MARKET", price=0.0, product="D"):
    """
    Places an order on Upstox.
    This function will only simulate order placement if DRY_RUN_MODE is True.
    """
    if DRY_RUN_MODE:
        alert_message = (
            f"DRY RUN: Would have placed {transaction_type} order for "
            f"{quantity} of {instrument_key} at {order_type} price {price}."
        )
        logger.info(alert_message)
        send_alert_to_mobile(alert_message)
        return "DRY_RUN_ORDER_ID" # Return a dummy ID in dry run mode

    try:
        order_params = upstox_client.PlaceOrderRequest(
            instrument_token=instrument_key,
            quantity=quantity,
            product=product,
            validity="DAY", # or "GTT" for Good Till Trigger orders
            order_type=order_type,
            transaction_type=transaction_type,
            price=price, # Required for LIMIT/SL orders
            tag="sensex_algo" # Optional tag for tracking
        )

        response = order_api.place_order(body=order_params)
        if response and response.status == 'success' and response.data and response.data.order_id:
            logger.info(f"Order placed: {response.data.order_id}, Status: {response.status}. Type: {transaction_type} {quantity} of {instrument_key}")
            send_alert_to_mobile(f"Bot: Order placed successfully!\nID: {response.data.order_id}\nType: {transaction_type} {quantity} {instrument_key}")
            return response.data.order_id
        else:
            logger.error(f"Failed to place order. Response: {response}")
            send_alert_to_mobile(f"Bot Alert: Failed to place order for {instrument_key}. Check logs. Response: {response}")
            return None
    except ApiException as e:
        logger.error(f"Upstox API Error placing order for {instrument_key}: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot Alert: Upstox API Error placing order for {instrument_key}. Error: {e}")
        return None
    except Exception as e:
        logger.critical(f"Critical error during order placement for {instrument_key}: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot CRITICAL: Unexpected error placing order for {instrument_key}. Check logs!")
        return None

def get_current_positions_from_upstox():
    """Fetches current short-term positions from Upstox.
    In DRY_RUN_MODE, this returns an empty list to simulate no open positions.
    """
    if DRY_RUN_MODE:
        logger.info("DRY RUN: Simulating no open positions.")
        return []

    try:
        positions_data = portfolio_api.get_positions(api_version="2.0") # Assuming V2 for positions too
        if positions_data and positions_data.data:
            # logger.debug(f"Raw positions data: {positions_data.data}") # For debugging
            logger.info(f"Fetched {len(positions_data.data)} current positions from Upstox.")
            return positions_data.data
        return []
    except ApiException as e:
        logger.error(f"Upstox API Error fetching positions: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot Alert: Upstox API Error fetching positions! {e}")
        return []
    except Exception as e:
        logger.critical(f"Critical unexpected error fetching positions: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot CRITICAL: Unexpected error fetching positions! {e}")
        return []

def get_ltp(instrument_key):
    """Fetches Last Traded Price for a given instrument.
    In DRY_RUN_MODE, this returns a dummy LTP or can be randomized.
    """
    if DRY_RUN_MODE:
        # For dry run, return a plausible dummy value
        # This will affect P&L calculation in dry run but allows the loop to run.
        dummy_ltp = 82300 + (time.time() % 100) - 50 # Oscillate around a value
        logger.debug(f"DRY RUN: Dummy LTP for {instrument_key}: {dummy_ltp}")
        return dummy_ltp

    try:
        # market_quote_api.get_ltp takes instrument_key as a list
        response = market_quote_api.get_ltp(instrument_key=[instrument_key], api_version="2.0") # Assuming V2 for LTP
        if response and response.data and instrument_key in response.data:
            ltp = response.data[instrument_key].last_price
            # logger.debug(f"Fetched LTP for {instrument_key}: {ltp}")
            return ltp
        logger.warning(f"Could not get LTP for {instrument_key}. Data missing in response.")
        return None
    except ApiException as e:
        logger.error(f"Upstox API Error fetching LTP for {instrument_key}: {e}", exc_info=True)
        # No alert for every LTP fetch error, as it can be frequent due to rate limits or temporary network issues
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching LTP for {instrument_key}: {e}", exc_info=True)
        return None

def get_option_chain_data(underlying_instrument_key, expiry_date):
    """Fetches option chain data for a given underlying and expiry."""
    if DRY_RUN_MODE:
        logger.info("DRY RUN: Skipping actual option chain data fetch.")
        return {} # Return empty dict in dry run

    try:
        # options_api.get_put_call_option_chain needs 'api_version'
        response = options_api.get_put_call_option_chain(
            instrument_key=underlying_instrument_key,
            expiry_date=expiry_date,
            api_version="2.0" # Assuming V2 for option chain
        )
        if response and response.data:
            logger.info(f"Fetched option chain for {underlying_instrument_key} {expiry_date}.")
            return response.data
        return None
    except ApiException as e:
        logger.error(f"Upstox API Error fetching option chain for {underlying_instrument_key} {expiry_date}: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot Alert: Upstox API Error fetching option chain! {e}")
        return None
    except Exception as e:
        logger.critical(f"Critical unexpected error fetching option chain: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot CRITICAL: Unexpected error fetching option chain! {e}")
        return None

def calculate_pnl(current_positions_data, fut_ltp, option_chain):
    """Calculates overall P&L based on fetched positions and current market data."""
    global daily_pnl # Update global P&L
    current_pnl = 0.0

    if not current_positions_data:
        daily_pnl = 0.0
        return 0.0 # No positions, so P&L is 0

    for pos in current_positions_data:
        instrument_key = pos.instrument_token # Upstox uses instrument_token in positions
        quantity = pos.quantity
        avg_price = pos.average_price
        transaction_type = pos.transaction_type # BUY or SELL

        if "FUT" in instrument_key: # Assuming 'FUT' is reliably in future instrument_keys
            current_price = fut_ltp
            if current_price is None: # Handle case where LTP couldn't be fetched
                logger.warning(f"Could not get current price for future {instrument_key}. Skipping P&L for this leg.")
                continue

            if transaction_type == "BUY":
                pnl = (current_price - avg_price) * quantity
            else: # SELL
                pnl = (avg_price - current_price) * quantity
            current_pnl += pnl

        elif "OPT" in instrument_key: # Assuming 'OPT' is reliably in option instrument_keys
            # For options, you'd usually get LTP from the market data stream.
            # If not streaming, fetch LTP for each option instrument_key.
            option_ltp = get_ltp(instrument_key)
            if option_ltp is None:
                logger.warning(f"Could not get current price for option {instrument_key}. Skipping P&L for this leg.")
                continue

            if transaction_type == "BUY":
                pnl = (option_ltp - avg_price) * quantity
            else: # SELL
                pnl = (avg_price - option_ltp) * quantity
            current_pnl += pnl

        # Add a placeholder for other instrument types if any
        else:
            logger.debug(f"Unhandled instrument type in P&L calculation: {instrument_key}")

    daily_pnl = current_pnl # Update global daily P&L
    return current_pnl

def close_all_positions():
    """Attempts to close all open positions.
    In DRY_RUN_MODE, this simulates closing positions.
    """
    logger.warning("Attempting to close all open positions due to critical event or shutdown.")
    send_alert_to_mobile("Bot: Initiating closure of all open positions.")

    positions_to_close = get_current_positions_from_upstox() # This will be empty in DRY_RUN_MODE
    if not positions_to_close:
        logger.info("No open positions found to close.")
        return

    for pos in positions_to_close:
        instrument_key = pos.instrument_token
        quantity = pos.quantity
        transaction_type = "SELL" if pos.transaction_type == "BUY" else "BUY" # Reverse transaction

        logger.info(f"Closing {transaction_type} {quantity} of {instrument_key} (Avg Price: {pos.average_price}).")
        # Call place_upstox_order which handles DRY_RUN_MODE
        place_upstox_order(instrument_key, quantity, transaction_type, order_type="MARKET", product=pos.product)
        time.sleep(1) # Small delay to avoid rate limit issues when closing multiple positions


# --- List Best Strategies Function ---
def list_best_strategies_to_telegram():
    """Lists down common F&O strategies to the Telegram chat."""
    strategies_message = (
        "📊 *Common F&O Strategies:*\n\n"
        "1.  *Long Futures/Calls/Puts*: Simple directional trades. High risk if market moves opposite.\n"
        "2.  *Short Straddle/Strangle*: Selling ATM/OTM options. Profits from time decay and low volatility. High risk if market moves sharply.\n"
        "3.  *Long Straddle/Strangle*: Buying ATM/OTM options. Profits from high volatility (large moves). Used before major events.\n"
        "4.  *Bull Call Spread*: Buy ITM/ATM Call, Sell OTM Call. Limited profit, limited loss. For moderately bullish view.\n"
        "5.  *Bear Put Spread*: Buy ITM/ATM Put, Sell OTM Put. Limited profit, limited loss. For moderately bearish view.\n"
        "6.  *Iron Condor*: Sell OTM Call spread \\+ Sell OTM Put spread. Profits from range-bound market. Limited profit, limited loss.\n" # Escaped +
        "7.  *Butterfly Spread*: Combines bull/bear spreads. Profits from very narrow range-bound movement around a specific strike. Limited profit, very limited loss.\n"
        "8.  *Covered Call*: Long stock \\+ Short Call. Income generation from holding stock, but caps upside.\n" # Escaped +
        "9.  *Protective Put*: Long stock \\+ Long Put. Protects downside of stock holdings.\n" # Escaped +
        "\n_Remember to always manage risk with Stop\\-Loss and proper position sizing!_" # Escaped hyphen
    )
    send_alert_to_mobile(strategies_message)
    logger.info("Listed best strategies to Telegram.")

# --- Strategy Implementation (Example: Simple Trend Following with Defined Risk) ---
# NOTE: This is a simplified example. Your actual strategy will require more sophisticated
# technical analysis, entry/exit signals, and potentially multi-leg option strategies.

def execute_sensex_strategy():
    global total_capital, daily_pnl, current_positions

    # Refresh capital
    total_capital = get_current_capital()
    if total_capital <= 0:
        logger.error("No available capital. Cannot execute strategy.")
        return

    # For weekly target, you might manage trades across days
    # This example focuses on a single entry/exit for simplicity.

    # 1. Define Sensex Future instrument key (dynamically, or as a global constant for this run)
    # This should ideally be fetched from Upstox's instrument master to get the latest expiry.
    # For a stable example, define it globally after fetching or looking up.
    # Replace with the actual instrument key you determined, e.g., from Upstox's "get_expiries" and "get_future_contracts" API.
    # Example: SENSEX_FUT_KEY = "BSE_FO|INDEX_FUT|SENSEX|20250630"
    # SENSEX_FUT_KEY will be a global variable assumed to be set for the duration of the bot run.
    # Let's define a placeholder here for the example to run. In a real scenario, this would be set once at startup
    # after querying Upstox for the active contract.

    # --- DUMMY SENSEX FUTURES KEY - REPLACE WITH REAL LOGIC ---
    # You would typically find the current month's Sensex Futures contract from the Upstox Instruments API.
    # For this example, let's assume a static key for demonstration purposes.
    # You need to dynamically find the correct future key for the current active expiry.
    current_expiry_date_obj = datetime.now() + timedelta(days=(4-datetime.now().weekday()+7)%7) # Next Thursday (approx for weekly)
    # Check actual BSE Sensex future expiry - usually last Friday of month
    # For BSE index F&O, recent changes suggest Tuesday for weekly, last Tuesday for monthly.
    # Reconfirm the specific June 2025 expiry for Sensex futures from Upstox documentation or your broker.
    # For this example, I'll set a plausible looking key:
    current_month_expiry_str = (datetime.now().replace(day=28) + timedelta(days=4)).strftime('%Y%m%d') # Dummy: assuming last Monday of June
    SENSEX_FUT_KEY_ACTIVE = get_sensex_instrument_key("FUT", current_month_expiry_str)
    if not SENSEX_FUT_KEY_ACTIVE:
        logger.error("Active Sensex Futures Instrument Key could not be determined. Skipping strategy execution.")
        return

    # 2. Get current Sensex Future LTP
    fut_ltp = get_ltp(SENSEX_FUT_KEY_ACTIVE)
    if not fut_ltp:
        logger.warning(f"Could not get LTP for Sensex Future {SENSEX_FUT_KEY_ACTIVE}. Skipping strategy for now.")
        return

    # --- Strategy Core: Simple Breakout Strategy (Illustrative) ---
    # This is where your intelligence goes.
    # Example: Buy if price breaks above a resistance, Sell if below support.
    # For a 1:2/1:3 R:R, you need predefined entry, stop-loss, and target levels based on analysis.

    # Dummy signals based on arbitrary levels (REPLACE WITH REAL TECHNICAL ANALYSIS)
    resistance_level = 82500
    support_level = 82000

    # Calculate trade size based on risk per trade
    risk_points_per_lot = 100 # Example: Willing to lose 100 Sensex points per lot
    target_profit_points_per_lot = risk_points_per_lot * RISK_REWARD_RATIO

    risk_per_lot_rupees = risk_points_per_lot * SENSEX_LOT_SIZE

    if risk_per_lot_rupees <= 0:
        logger.error("Calculated risk per lot is zero or negative. Check SENSEX_LOT_SIZE or risk_points_per_lot.")
        return

    # Calculate number of lots based on capital and risk per trade
    num_lots_to_trade = int((total_capital * RISK_PER_TRADE_PERCENT) / risk_per_lot_rupees)
    num_lots_to_trade = max(1, num_lots_to_trade) # Ensure at least 1 lot if conditions allow

    # Ensure current_positions global reflects actual Upstox positions
    # (The run_bot loop calls get_current_positions_from_upstox() which will update it)
    has_open_position = bool(current_positions) # Check if any position is tracked locally

    # Entry Logic
    if not has_open_position:
        if fut_ltp > resistance_level: # Bullish Breakout Signal
            logger.info(f"Bullish breakout detected ({fut_ltp} > {resistance_level}). Attempting to BUY.")
            sl_price = fut_ltp - risk_points_per_lot
            tp_price = fut_ltp + target_profit_points_per_lot

            order_id = place_upstox_order(SENSEX_FUT_KEY_ACTIVE, num_lots_to_trade * SENSEX_LOT_SIZE, "BUY", product="NORMAL")
            if order_id:
                # Only update current_positions if not in DRY_RUN_MODE or for simulation purposes
                if not DRY_RUN_MODE:
                    current_positions[SENSEX_FUT_KEY_ACTIVE] = {
                        'quantity': num_lots_to_trade * SENSEX_LOT_SIZE,
                        'avg_price': fut_ltp, # Actual fill price might differ
                        'side': 'BUY',
                        'stop_loss_price': sl_price,
                        'take_profit_price': tp_price
                    }
                logger.info(f"Opened LONG Sensex Futures. SL: {sl_price}, TP: {tp_price}")
                send_alert_to_mobile(f"Bot: Opened LONG Sensex Futures @ {fut_ltp}. SL: {sl_price}, TP: {tp_price}")

        elif fut_ltp < support_level: # Bearish Breakdown Signal
            logger.info(f"Bearish breakdown detected ({fut_ltp} < {support_level}). Attempting to SELL.")
            sl_price = fut_ltp + risk_points_per_lot
            tp_price = fut_ltp - target_profit_points_per_lot

            order_id = place_upstox_order(SENSEX_FUT_KEY_ACTIVE, num_lots_to_trade * SENSEX_LOT_SIZE, "SELL", product="NORMAL")
            if order_id:
                # Only update current_positions if not in DRY_RUN_MODE or for simulation purposes
                if not DRY_RUN_MODE:
                    current_positions[SENSEX_FUT_KEY_ACTIVE] = {
                        'quantity': num_lots_to_trade * SENSEx_LOT_SIZE,
                        'avg_price': fut_ltp,
                        'side': 'SELL',
                        'stop_loss_price': sl_price,
                        'take_profit_price': tp_price
                    }
                logger.info(f"Opened SHORT Sensex Futures. SL: {sl_price}, TP: {tp_price}")
                send_alert_to_mobile(f"Bot: Opened SHORT Sensex Futures @ {fut_ltp}. SL: {sl_price}, TP: {tp_price}")

    # Position Management (SL/TP for open positions)
    # Iterate through a copy as positions might be deleted
    positions_to_check = list(current_positions.keys())
    for inst_key in positions_to_check:
        if inst_key == SENSEX_FUT_KEY_ACTIVE: # Only manage the future for now
            pos = current_positions[inst_key]

            # Re-fetch LTP just before checking SL/TP for accuracy
            current_ltp_for_pos = get_ltp(inst_key)
            if current_ltp_for_pos is None:
                logger.warning(f"Could not get current LTP for {inst_key} for SL/TP check. Skipping.")
                continue

            if pos['side'] == 'BUY':
                if current_ltp_for_pos <= pos['stop_loss_price']:
                    logger.warning(f"Stop Loss HIT for LONG {inst_key} at {current_ltp_for_pos}. Closing position.")
                    send_alert_to_mobile(f"Bot: SL HIT for LONG {inst_key} @ {current_ltp_for_pos}!")
                    place_upstox_order(inst_key, pos['quantity'], "SELL", order_type="MARKET", product="NORMAL")
                    # If not DRY_RUN_MODE, delete from local tracking after real closure
                    if not DRY_RUN_MODE:
                        del current_positions[inst_key]
                elif current_ltp_for_pos >= pos['take_profit_price']:
                    logger.info(f"Take Profit HIT for LONG {inst_key} at {current_ltp_for_pos}. Closing position.")
                    send_alert_to_mobile(f"Bot: TP HIT for LONG {inst_key} @ {current_ltp_for_pos}!")
                    place_upstox_order(inst_key, pos['quantity'], "SELL", order_type="MARKET", product="NORMAL")
                    # If not DRY_RUN_MODE, delete from local tracking after real closure
                    if not DRY_RUN_MODE:
                        del current_positions[inst_key]

            elif pos['side'] == 'SELL':
                if current_ltp_for_pos >= pos['stop_loss_price']:
                    logger.warning(f"Stop Loss HIT for SHORT {inst_key} at {current_ltp_for_pos}. Closing position.")
                    send_alert_to_mobile(f"Bot: SL HIT for SHORT {inst_key} @ {current_ltp_for_pos}!")
                    place_upstox_order(inst_key, pos['quantity'], "BUY", order_type="MARKET", product="NORMAL")
                    # If not DRY_RUN_MODE, delete from local tracking after real closure
                    if not DRY_RUN_MODE:
                        del current_positions[inst_key]
                elif current_ltp_for_pos <= pos['take_profit_price']:
                    logger.info(f"Take Profit HIT for SHORT {inst_key} at {current_ltp_for_pos}. Closing position.")
                    send_alert_to_mobile(f"Bot: TP HIT for SHORT {inst_key} @ {current_ltp_for_pos}!")
                    place_upstox_order(inst_key, pos['quantity'], "BUY", order_type="MARKET", product="NORMAL")
                    # If not DRY_RUN_MODE, delete from local tracking after real closure
                    if not DRY_RUN_MODE:
                        del current_positions[inst_key]

                        # Optional: Add logic for options spreads here if you integrate them later
    # E.g., check individual option legs for SL/TP or overall spread P&L.


# --- Main Bot Execution Flow ---
def run_bot():
    logger.info("Starting Upstox Sensex F&O Trading Bot...")
    send_alert_to_mobile("Bot: Trading system starting up.")

    load_pnl_history() # Load P&L history at startup

    global total_capital # Make sure total_capital is declared global before assigning
    try:
        total_capital = get_current_capital()
        if total_capital <= 0:
            logger.critical("No available capital or failed to fetch. Exiting bot.")
            send_alert_to_mobile("Bot CRITICAL: No available capital. Shutting down!")
            sys.exit(1)
        logger.info(f"Initial Capital: {total_capital:.2f}")
        send_alert_to_mobile(f"Bot: Initial Capital: INR {total_capital:.2f}")

    except Exception as e:
        logger.critical(f"Failed to initialize capital: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot CRITICAL: Failed to get capital at startup. {e}")
        sys.exit(1)

    # List best strategies to Telegram (one-time call at startup)
    list_best_strategies_to_telegram()

    # Resolve SENSEX_FUT_KEY_ACTIVE once at startup
    # This needs to be dynamically fetched for the correct contract month/week
    # For now, it's a dummy value in get_sensex_instrument_key
    # In a real system:
    # SENSEX_INDEX_KEY = "BSE_INDEX|SENSEX" # This is for Sensex spot index
    # active_fut_expiry_date = get_latest_future_expiry_date_from_upstox() # Need to implement this
    # SENSEX_FUT_KEY_ACTIVE = get_sensex_instrument_key("FUT", active_fut_expiry_date.strftime('%Y%m%d')) # Placeholder for real key

    # Main trading loop
    try:
        last_graph_minute = -1 # To avoid generating multiple graphs in the same minute
        while is_market_open():
            current_time = datetime.now()

            # Get actual positions from Upstox (more reliable than local tracking)
            # NOTE: For proper position tracking, you'd constantly update `current_positions`
            # based on order confirmations and trade fills via Websocket or polling order book.
            # For simplicity, this example only updates on `execute_sensex_strategy` for entries.
            # Real bots would reconcile actual broker positions frequently.
            upstox_raw_positions = get_current_positions_from_upstox()

            # Recalculate P&L based on live data
            # SENSEX_FUT_KEY_ACTIVE must be determined by your get_sensex_instrument_key logic
            # This depends on which futures contract you intend to trade (current month, next month etc)
            current_fut_ltp = get_ltp(SENSEX_FUT_KEY_ACTIVE)
            if current_fut_ltp is None:
                logger.warning("Could not get Sensex Future LTP for P&L calculation. Skipping.")
                time.sleep(5)
                continue # Skip this iteration if LTP not available

            current_overall_pnl = calculate_pnl(upstox_raw_positions, current_fut_ltp, None) # option_chain is None for now
            logger.info(f"Current Overall P&L: {current_overall_pnl:.2f}. Daily P&L: {daily_pnl:.2f}")
            update_pnl_history(current_overall_pnl, total_capital) # Update P&L history

            # Check daily loss limit
            daily_loss_limit_rupees = -(total_capital * MAX_DAILY_LOSS_PERCENT)
            if daily_pnl < daily_loss_limit_rupees:
                logger.critical(f"Daily loss limit ({MAX_DAILY_LOSS_PERCENT*100}%) exceeded (INR {daily_pnl:.2f} < {daily_loss_limit_rupees:.2f}). Shutting down for the day.")
                send_alert_to_mobile(f"Bot CRITICAL: Daily loss limit HIT (INR {daily_pnl:.2f})! Exiting all positions and stopping.")
                close_all_positions() # This needs to exit all open positions
                break # Stop trading for the day

            # Check weekly profit target
            # This requires consistent P&L data across days. You'd sum up daily P&Ls or use a cumulative sum.
            # For simplicity, if current_overall_pnl from a single trade is enough, you could check that.
            # If current_overall_pnl >= DESIRED_WEEKLY_PROFIT and has_open_position: # Simplified check
            #     logger.info(f"Weekly profit target (INR {DESIRED_WEEKLY_PROFIT}) achieved! Current P&L: {current_overall_pnl:.2f}. Stopping trading for the week.")
            #     send_alert_to_mobile(f"Bot: Weekly profit target ACHIEVED (INR {current_overall_pnl:.2f})! Stopping trading for the week.")
            #     close_all_positions()
            #     break # Stop for the week (or for the day if market hours still open)

            execute_sensex_strategy() # Run your defined strategy logic

            # Generate graph periodically (e.g., every 30 minutes)
            if current_time.minute % 30 == 0 and current_time.minute != last_graph_minute:
                generate_pnl_graph()
                last_graph_minute = current_time.minute # Update last graph minute to prevent multiple graphs in same minute

            time.sleep(10) # Poll every 10 seconds (adjust as needed, consider Upstox rate limits)

    except KeyboardInterrupt:
        logger.info("Bot manually stopped via KeyboardInterrupt.")
        send_alert_to_mobile("Bot: Manual shutdown initiated. Attempting to close positions.")
        close_all_positions()
    except Exception as outer_e:
        logger.critical(f"Unhandled critical error in main loop, bot shutting down: {outer_e}", exc_info=True)
        send_alert_to_mobile(f"Bot CRITICAL: Unhandled error, shutting down! {outer_e}")
        close_all_positions() # Attempt to close positions before exiting
        sys.exit(1) # Exit with an error code

    finally:
        logger.info("Upstox Sensex F&O Trading Bot gracefully stopped.")
        send_alert_to_mobile("Bot: Trading system stopped.")
        generate_pnl_graph() # Generate final graph
        save_pnl_history() # Ensure P&L history is saved

def is_market_open():
    """Checks if the Indian F&O market is currently open."""
    now = datetime.now()
    # Indian Standard Time (IST)
    # Market generally opens 9:15 AM and closes 3:30 PM for F&O
    market_start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end_time = now.replace(hour=15, minute=30, second=0, microsecond=0)

    # Check for weekends
    if now.weekday() >= 5: # Saturday (5) or Sunday (6)
        return False

    # Check for market holidays (you'd need to fetch these via Upstox API or a holiday calendar)
    # Example: if check_for_holiday(now.date()): return False

    # Check if current time is within market hours
    return market_start_time <= now <= market_end_time

# --- Main execution point ---
if __name__ == "__main__":
    # It's HIGHLY RECOMMENDED to load these from environment variables
    # or a secure config file, NOT hardcoded.
    # E.g.: API_KEY = os.getenv("UPSTOX_API_KEY")
    #       TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

    if not API_KEY or not API_SECRET or not ACCESS_TOKEN:
        logger.error("API_KEY, API_SECRET, or ACCESS_TOKEN not configured. Please set them.")
        logger.error("Refer to Upstox API documentation for authentication setup.")
        sys.exit(1)

    if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN" or TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_CHAT_ID":
        logger.warning("Telegram bot credentials are not set. Alerts will not be sent.")

    # A dummy global to hold the active Sensex future key for strategy.
    # In a real bot, this would be dynamically set at startup by querying Upstox's instrument master.
    # Example: SENSEX_FUT_KEY_ACTIVE = get_sensex_instrument_key("FUT", (datetime.now() + timedelta(days=20)).strftime('%Y%m%d'))
    # For now, let's just make sure it's defined.
    # It's set within execute_sensex_strategy for now but should be globally available/resolved
    # at the start of the trading day.

    # You might want to resolve this once at the start of `run_bot` and pass it around
    # or keep it as a global that `get_sensex_instrument_key` properly sets.
    # For this current structure, I will keep the call to `get_sensex_instrument_key`
    # inside `execute_sensex_strategy` as it assumes it can get the latest current expiry.

    run_bot()

