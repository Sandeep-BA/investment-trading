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
import threading # For running Flask in a separate thread
from flask import Flask, render_template, jsonify # Modified: Use render_template

# Disable insecure request warnings globally for urllib3
# ⚠️⚠️⚠️ SECURITY WARNING: This disables SSL certificate verification globally.
# Use this with EXTREME CAUTION and only if you understand the security implications.
# The ideal solution is to properly configure your system's SSL certificate trust chain.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ⚠️⚠️⚠️ EXTREMELY IMPORTANT SECURITY WARNING ⚠️⚠️⚠️
# NEVER HARDCODE API KEYS, SECRETS, OR ACCESS TOKENS IN PRODUCTION CODE.
# THIS IS FOR DEMONSTRATION/TESTING PURPOSES ONLY.
# For production, use environment variables (e.g., os.getenv("UPSTOX_API_KEY"))
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

# --- Flask App Configuration ---
# MODIFIED: Explicitly define template_folder using os.path.join and os.path.dirname(__file__)
# This makes the path relative to the current script's directory, regardless of where the script is executed from.
current_script_dir = os.path.dirname(__file__)
template_dir = os.path.join(current_script_dir, 'sensex-derivative', 'templates')
app = Flask(__name__, template_folder=template_dir)


# Global variable to store bot status and data for Flask UI
bot_status_data = {
    "status": "Initializing",
    "overall_current_pnl": 0.0,
    "overall_daily_pnl": 0.0,
    "current_positions_for_ui": [], # List of dicts for UI display
    "orders_for_ui": [],
    "trades_for_ui": [],
    "last_updated": datetime.now().isoformat(),
    "dry_run_mode": True, # Updated by the DRY_RUN_MODE constant
    "risk_per_trade_percent": 0.0, # Updated by the constant
    "max_daily_loss_percent": 0.0, # Updated by the constant
    "risk_reward_ratio": 0.0, # Updated by the constant
    "capital_details": {
        "initial_capital": 0.0,
        "available_margin": 0.0,
        "used_margin": 0.0,
        "unrealised_pnl": 0.0,
        "realised_pnl": 0.0,
    },
    "logs": [] # To capture recent logs for UI
}

# --- Logging Setup ---
# Create a custom logger
logger = logging.getLogger('SensexTradingBot')
logger.setLevel(logging.INFO) # Set default logging level for the logger

# Create handlers
# Console handler (logs to terminal)
c_handler = logging.StreamHandler(sys.stdout)
# File handler (logs to file, rotates daily, keeps 7 days)
f_handler = TimedRotatingFileHandler("trading_bot.log", when="midnight", interval=1, backupCount=7)

# Custom handler to send logs to the Flask UI data
class UIStreamHandler(logging.Handler):
    """
    A custom logging handler that appends log records to a global list
    (bot_status_data["logs"]) for display in the Flask UI.
    """
    def emit(self, record):
        # Only store INFO and above to avoid too much data in UI, or critical messages.
        # This prevents UI from being overwhelmed with DEBUG level messages.
        if record.levelno >= logging.INFO or record.levelno >= logging.CRITICAL:
            bot_status_data["logs"].append(self.format(record))
            # Keep log list size manageable to prevent excessive memory usage
            if len(bot_status_data["logs"]) > 50:
                bot_status_data["logs"] = bot_status_data["logs"][-50:]

ui_handler = UIStreamHandler()
ui_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Add handlers to the logger
logger.addHandler(c_handler)
logger.addHandler(f_handler)
logger.addHandler(ui_handler) # Add UI stream handler for Flask UI

# --- Trading Parameters ---
SENSEX_FUT_SYMBOL_PATTERN = "SENSEX" # Part of the trading symbol or name
SENSEX_LOT_SIZE = 10 # Confirmed lot size for Sensex Futures and Options
DESIRED_WEEKLY_PROFIT = 75000.0
MAX_DAILY_LOSS_PERCENT = 0.02 # 2% of capital
RISK_PER_TRADE_PERCENT = 0.01 # 1% of capital per trade
RISK_REWARD_RATIO = 2.0 # Aim for 1:2 or 1:3 as desired, e.g., 2.0 or 3.0

# Flag to control actual order execution vs. dry run/alerting only
DRY_RUN_MODE = True # Set to False to enable actual trading
bot_status_data["dry_run_mode"] = DRY_RUN_MODE # Update UI status from constant
bot_status_data["risk_per_trade_percent"] = RISK_PER_TRADE_PERCENT
bot_status_data["max_daily_loss_percent"] = MAX_DAILY_LOSS_PERCENT
bot_status_data["risk_reward_ratio"] = RISK_REWARD_RATIO

# Global state for positions and P&L (in a real system, consider a database for persistence)
# This dictionary will hold the bot's current understanding of open positions
current_positions = {} # {instrument_key: {'quantity': N, 'avg_price': M, 'side': 'BUY'/'SELL', 'stop_loss_price': SL, 'take_profit_price': TP, 'ltp': LTP, 'pnl_per_position': PNL}}
total_capital = 0.0 # Will be fetched from Upstox API
daily_pnl = 0.0 # Tracks daily P&L for loss limit checks

# P&L History for Graphing
pnl_history_file = "pnl_history.json"
pnl_data = [] # List of {'timestamp': '...', 'pnl': X, 'capital': Y}

# --- Upstox API Client Initialization ---
# Ensure ApiException is imported correctly for error handling
from upstox_client.rest import ApiException

api_client = upstox_client.ApiClient()
api_client.configuration.access_token = ACCESS_TOKEN
# Disabling SSL verification for Upstox API calls due to environment issues.
# Please try to resolve the underlying SSL certificate issues for production use.
api_client.verify_ssl = False

# Initialize specific API instances for different Upstox functionalities
login_api = upstox_client.LoginApi(api_client)
market_quote_api = upstox_client.MarketQuoteApi(api_client)
market_quote_v3_api = upstox_client.MarketQuoteV3Api(api_client) # Used for Option Greeks, if implemented
order_api = upstox_client.OrderApi(api_client)
portfolio_api = upstox_client.PortfolioApi(api_client)
user_api = upstox_client.UserApi(api_client)
history_api = upstox_client.HistoryApi(api_client) # Used for historical data
options_api = upstox_client.OptionsApi(api_client) # Used for option chain details

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
        'parse_mode': 'Markdown' # Use Markdown for basic formatting like bold/italic
    }
    try:
        # requests.post with verify=False due to SSL issues, see global warning
        response = requests.post(url, json=payload, verify=False)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        logger.info(f"Telegram alert sent: {message[:50]}...") # Log first 50 chars of the alert
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Telegram alert: {e}", exc_info=True)
        if 'response' in locals() and hasattr(response, 'text'):
            logger.error(f"Telegram API response: {response.text}")
        # Avoid recursive alerts if the alert system itself is failing

def load_pnl_history():
    """Loads P&L history from a JSON file for graph generation."""
    global pnl_data
    if os.path.exists(pnl_history_file):
        try:
            with open(pnl_history_file, 'r') as f:
                pnl_data = json.load(f)
            logger.info("P&L history loaded from file.")
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
        logger.info("P&L history saved to file.")
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


def get_current_capital_and_pnl_details():
    """
    Fetches comprehensive margin and P&L details from Upstox.
    Returns dummy data in DRY_RUN_MODE.
    Returns a dictionary: {'available_margin', 'used_margin', 'unrealised_pnl', 'realised_pnl'}
    """
    if DRY_RUN_MODE:
        # Simulate some fluctuating capital and P&L for dry run UI
        # Correctly convert os.urandom.hex() to an integer before modulo
        available = 100000.0 + (int(os.urandom(8).hex(), 16) % 10000) - 5000
        used = 10000.0 + (int(os.urandom(8).hex(), 16) % 2000) - 1000
        unrealised = (int(os.urandom(8).hex(), 16) % 5000) - 2500
        realised = (int(os.urandom(8).hex(), 16) % 10000) - 5000 # Can be positive or negative

        logger.debug(f"DRY RUN: Simulating funds - Available: {available:.2f}, Used: {used:.2f}, Unrealized: {unrealised:.2f}, Realized: {realised:.2f}")
        return {
            'initial_capital': 100000.0, # Initial capital is a fixed dummy in dry run
            'available_margin': available,
            'used_margin': used,
            'unrealised_pnl': unrealised,
            'realised_pnl': realised
        }

    try:
        logger.info("Attempting to fetch real-time funds and P&L details from Upstox API.")
        funds_data = user_api.get_user_fund_margin(segment="FUTURES", api_version="2.0")

        details = {
            'initial_capital': total_capital, # This would ideally be loaded from a persistent store for true initial capital
            'available_margin': 0.0,
            'used_margin': 0.0,
            'unrealised_pnl': 0.0,
            'realised_pnl': 0.0
        }

        if hasattr(funds_data.data, 'equity'): # Example for equity segment structure
            eq_data = funds_data.data.equity
            details['available_margin'] = getattr(eq_data, 'available_margin', 0.0)
            details['used_margin'] = getattr(eq_data, 'used_margin', 0.0)
            details['unrealised_pnl'] = getattr(eq_data, 'unrealised_pnl', 0.0)
            details['realised_pnl'] = getattr(eq_data, 'realised_pnl', 0.0)
            logger.debug(f"Funds from equity segment: {details}")
        elif hasattr(funds_data.data, 'fno'): # Example for F&O segment structure
            fno_data = funds_data.data.fno
            details['available_margin'] = getattr(fno_data, 'available_margin', 0.0)
            details['used_margin'] = getattr(fno_data, 'used_margin', 0.0)
            details['unrealised_pnl'] = getattr(fno_data, 'unrealised_pnl', 0.0)
            details['realised_pnl'] = getattr(fno_data, 'realised_pnl', 0.0)
            logger.debug(f"Funds from F&O segment: {details}")
        else:
            logger.warning("Could not find detailed margin data in standard equity or F&O paths. Logging full response for debugging.")
            logger.debug(f"Full funds data structure: {funds_data}") # Log full structure for debugging if needed

        logger.info(f"Fetched funds - Available: {details['available_margin']:.2f}, Used: {details['used_margin']:.2f}, Unrealized: {details['unrealised_pnl']:.2f}, Realized: {details['realised_pnl']:.2f}")
        return details
    except ApiException as e:
        logger.error(f"Upstox API Error while fetching funds: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot Alert: Upstox API Error on funds fetch! {e}")
        return {
            'initial_capital': total_capital, # Keep current total_capital if fetch fails
            'available_margin': 0.0, 'used_margin': 0.0, 'unrealised_pnl': 0.0, 'realised_pnl': 0.0
        }
    except Exception as e:
        logger.critical(f"Critical unexpected error fetching funds: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot CRITICAL: Unexpected error fetching funds! {e}")
        return {
            'initial_capital': total_capital,
            'available_margin': 0.0, 'used_margin': 0.0, 'unrealised_pnl': 0.0, 'realised_pnl': 0.0
        }

def get_sensex_instrument_key(instrument_type, expiry_date_str, strike_price=None, option_type=None):
    """
    Placeholder: Dynamically finds the instrument_key for Sensex Futures or Options.
    In a real bot, you would use Upstox's get_instrument_by_symbol, get_option_contracts,
    or download/process the full instrument master file.
    """
    logger.warning("get_sensex_instrument_key is a placeholder. Implement robust instrument lookup using Upstox API.")

    # Dummy implementation for demonstration purposes.
    # YOU MUST REPLACE THIS WITH REAL LOGIC TO FETCH THE CORRECT, ACTIVE INSTRUMENT KEY.
    # For Sensex, futures expire last Monday of the expiry month (effective from Sep 2025 onwards, re-verify).
    # For weekly options, specific days apply.

    if instrument_type == "FUT":
        logger.debug(f"Returning dummy futures key for expiry {expiry_date_str}")
        return "BSE_FO|INDEX_FUT|SENSEX|20250630" # Example: June 30th 2025 expiry
    elif instrument_type == "OPT":
        logger.debug(f"Returning dummy options key for expiry {expiry_date_str}, strike {strike_price}, type {option_type}")
        return f"BSE_FO|INDEX_OPT|SENSEX|{expiry_date_str.replace('-', '')}|{int(strike_price)}|{option_type}"
    logger.error(f"Could not determine instrument key for type {instrument_type}.")
    return None

def place_upstox_order(instrument_key, quantity, transaction_type, order_type="MARKET", price=0.0, product="D"):
    """
    Places an order on Upstox. Simulates order placement if DRY_RUN_MODE is True.
    product: 'D' (Delivery/Normal), 'I' (Intraday), 'CO' (Cover Order), 'BO' (Bracket Order)
    """
    if DRY_RUN_MODE:
        order_id = f"DRY_RUN_ORDER_{int(time.time() * 1000)}"
        alert_message = (
            f"DRY RUN: Would have placed {transaction_type} order for "
            f"{quantity} of {instrument_key} at {order_type} price {price:.2f}. Order ID: {order_id}"
        )
        logger.info(alert_message)
        send_alert_to_mobile(alert_message)

        global current_positions
        current_positions[instrument_key] = {
            'instrument_key': instrument_key, # Added for consistency with UI positions
            'quantity': quantity,
            'avg_price': price, # Use price as dummy avg_price for dry run
            'side': transaction_type,
            'stop_loss_price': 0.0, # Dummy SL/TP for dry run
            'take_profit_price': 0.0  # Dummy SL/TP for dry run
        }
        # Add to dummy orders_for_ui
        bot_status_data["orders_for_ui"].append({
            'order_id': order_id,
            'instrument_key': instrument_key,
            'type': f"{transaction_type} {order_type}",
            'status': 'DRY_RUN_PLACED'
        })
        # Simulate a trade being executed immediately
        bot_status_data["trades_for_ui"].append({
            'trade_id': f"DRY_RUN_TRADE_{int(time.time() * 1000) + 1}",
            'instrument_key': instrument_key,
            'quantity': quantity,
            'price': price
        })
        logger.debug(f"Dry run order placed. current_positions: {current_positions}")
        return order_id

    try:
        logger.info(f"Placing real order: {transaction_type} {quantity} of {instrument_key} at {order_type}.")
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
            # In a real scenario, you'd process webhooks or poll order book to update local positions/order book
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
    """Fetches current short-term positions from Upstox. Returns local `current_positions` in DRY_RUN_MODE."""
    if DRY_RUN_MODE:
        logger.debug("DRY RUN: Simulating open positions from local tracking.")
        # In dry run, current_positions is a dict where values are already formatted for UI.
        # We also added 'instrument_key' to the dict when placing dry run orders.
        return list(current_positions.values())

    try:
        logger.info("Fetching real-time current positions from Upstox API.")
        positions_data = portfolio_api.get_positions(api_version="2.0")
        if positions_data and positions_data.data:
            logger.info(f"Fetched {len(positions_data.data)} current positions from Upstox.")
            # For real positions, ensure consistency with the structure expected by calculate_pnl
            # and current_positions_for_ui
            return positions_data.data
        logger.info("No open positions found via Upstox API.")
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
    """Fetches Last Traded Price for a given instrument. Returns a dummy LTP in DRY_RUN_MODE."""
    if DRY_RUN_MODE:
        # For dry run, return a plausible dummy value that fluctuates around base Sensex
        dummy_ltp = 82300 + (int(os.urandom(8).hex(), 16) % 200) - 100
        logger.debug(f"DRY RUN: Dummy LTP for {instrument_key}: {dummy_ltp:.2f}")
        return dummy_ltp

    try:
        logger.debug(f"Fetching LTP for {instrument_key} from Upstox API.")
        response = market_quote_api.get_ltp(instrument_key=[instrument_key], api_version="2.0")
        if response and response.data and instrument_key in response.data:
            ltp = response.data[instrument_key].last_price
            logger.debug(f"Fetched LTP for {instrument_key}: {ltp:.2f}")
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
    """Fetches option chain data for a given underlying and expiry. Returns empty dict in DRY_RUN_MODE."""
    if DRY_RUN_MODE:
        logger.info("DRY RUN: Skipping actual option chain data fetch for option chain.")
        return {} # Return empty dict in dry run

    try:
        logger.info(f"Fetching option chain for {underlying_instrument_key} {expiry_date} from Upstox API.")
        response = options_api.get_put_call_option_chain(
            instrument_key=underlying_instrument_key,
            expiry_date=expiry_date,
            api_version="2.0"
        )
        if response and response.data:
            logger.info(f"Fetched option chain for {underlying_instrument_key} {expiry_date}.")
            logger.debug(f"Option chain data: {response.data}")
            return response.data
        logger.warning(f"No option chain data found for {underlying_instrument_key} {expiry_date}.")
        return None
    except ApiException as e:
        logger.error(f"Upstox API Error fetching option chain for {underlying_instrument_key} {expiry_date}: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot Alert: Upstox API Error fetching option chain! {e}")
        return None
    except Exception as e:
        logger.critical(f"Critical unexpected error fetching option chain: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot CRITICAL: Unexpected error fetching option chain! {e}")
        return None

def calculate_pnl(current_positions_raw_data, fut_ltp, option_chain):
    """
    Calculates overall P&L based on fetched raw positions and current market data.
    Also updates individual position details (LTP, P&L) for UI display.
    """
    global daily_pnl
    overall_pnl = 0.0
    positions_for_ui = [] # To store structured data for UI

    if not current_positions_raw_data:
        daily_pnl = 0.0 # Reset if no positions
        bot_status_data["current_positions_for_ui"] = []
        logger.debug("No current positions to calculate P&L.")
        return 0.0

    for pos_raw in current_positions_raw_data:
        # In dry run, pos_raw is already a dict from local 'current_positions'.
        # In real mode, it's an object from Upstox SDK (e.g., pos.instrument_token).
        if isinstance(pos_raw, dict):
            instrument_key = pos_raw.get('instrument_key')
            quantity = pos_raw.get('quantity')
            avg_price = pos_raw.get('avg_price')
            transaction_type = pos_raw.get('side')
            product_type = pos_raw.get('product', 'NORMAL') # Default to NORMAL if not specified in dry run
        else: # Assuming Upstox SDK object
            instrument_key = pos_raw.instrument_token
            quantity = pos_raw.quantity
            avg_price = pos_raw.average_price
            transaction_type = pos_raw.transaction_type
            product_type = pos_raw.product

        current_price = None
        if "FUT" in str(instrument_key): # Check 'FUT' in string form
            current_price = fut_ltp
            logger.debug(f"Using futures LTP {fut_ltp:.2f} for {instrument_key}")
        elif "OPT" in str(instrument_key): # Check 'OPT' in string form
            current_price = get_ltp(instrument_key) # Fetch LTP for options individually
            logger.debug(f"Using options LTP {current_price:.2f} for {instrument_key}")

        if current_price is None: # Correct Pythonic way to check for None
            logger.warning(f"Could not get current price for {instrument_key}. Skipping P&L for this leg.")
            continue

        pnl_per_position = 0.0
        if transaction_type == "BUY":
            pnl_per_position = (current_price - avg_price) * quantity
        else: # SELL
            pnl_per_position = (avg_price - current_price) * quantity

        overall_pnl += pnl_per_position

        # Update position for UI display
        # Use locally tracked SL/TP if available, otherwise default
        local_pos_details = current_positions.get(instrument_key, {})

        positions_for_ui.append({
            'instrument_key': instrument_key,
            'quantity': quantity,
            'avg_price': avg_price,
            'ltp': current_price,
            'side': transaction_type,
            'stop_loss_price': local_pos_details.get('stop_loss_price', 0.0),
            'take_profit_price': local_pos_details.get('take_profit_price', 0.0),
            'pnl_per_position': pnl_per_position
        })
    logger.info(f"Calculated overall P&L: {overall_pnl:.2f}. Updated {len(positions_for_ui)} positions for UI.")

    daily_pnl = overall_pnl
    bot_status_data["current_positions_for_ui"] = positions_for_ui # Update global UI data
    return overall_pnl

def close_all_positions():
    """Attempts to close all open positions. Simulates closing in DRY_RUN_MODE."""
    logger.warning("Attempting to close all open positions due to critical event or shutdown.")
    send_alert_to_mobile("Bot: Initiating closure of all open positions.")

    positions_to_close = get_current_positions_from_upstox() # This fetches real or simulated positions
    if not positions_to_close:
        logger.info("No open positions found to close.")
        return

    for pos in positions_to_close:
        # Handle pos as dict (from dry run) or object (from real API)
        if isinstance(pos, dict):
            instrument_key = pos.get('instrument_key')
            quantity = pos.get('quantity')
            transaction_type = "SELL" if pos.get('side') == "BUY" else "BUY" # Reverse transaction
            product_type = pos.get('product', "NORMAL") # Default for dry run
            avg_price = pos.get('avg_price')
        else:
            instrument_key = pos.instrument_token
            quantity = pos.quantity
            transaction_type = "SELL" if pos.transaction_type == "BUY" else "BUY" # Reverse transaction
            product_type = pos.product
            avg_price = pos.average_price

        logger.info(f"Closing {transaction_type} {quantity} of {instrument_key} (Avg Price: {avg_price:.2f}).")
        # Call place_upstox_order which respects DRY_RUN_MODE
        order_id = place_upstox_order(instrument_key, quantity, transaction_type, order_type="MARKET", product=product_type)
        if order_id and DRY_RUN_MODE: # If dry run, update local positions
            if instrument_key in current_positions:
                logger.debug(f"Removing {instrument_key} from local dry run positions.")
                del current_positions[instrument_key]
        time.sleep(1) # Small delay to avoid rate limit issues when closing multiple positions


# --- List Best Strategies Function (Sends to Telegram) ---
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
    # The get_current_capital_and_pnl_details now updates the total_capital and more details for UI
    capital_details = get_current_capital_and_pnl_details()
    total_capital = capital_details['available_margin'] # Use available margin as effective capital for trading decisions
    bot_status_data["capital_details"] = capital_details # Update UI capital details
    logger.debug(f"Strategy execution cycle. Available Capital: {total_capital:.2f}")

    if total_capital <= 0:
        logger.error("No available capital for strategy execution. Skipping trade opportunities.")
        return

    # 1. Define Sensex Future instrument key (dynamically, or as a global constant for this run)
    current_month_expiry_str = (datetime.now().replace(day=28) + timedelta(days=4)).strftime('%Y%m%d')
    global SENSEX_FUT_KEY_ACTIVE
    SENSEX_FUT_KEY_ACTIVE = get_sensex_instrument_key("FUT", current_month_expiry_str)
    if not SENSEX_FUT_KEY_ACTIVE:
        logger.error("Active Sensex Futures Instrument Key could not be determined. Skipping strategy execution.")
        return

    # 2. Get current Sensex Future LTP
    fut_ltp = get_ltp(SENSEX_FUT_KEY_ACTIVE)
    if not fut_ltp:
        logger.warning(f"Could not get LTP for Sensex Future {SENSEX_FUT_KEY_ACTIVE}. Skipping strategy for now.")
        return

    logger.info(f"Current Sensex Futures LTP: {fut_ltp:.2f}")

    # --- Strategy Core: Simple Breakout Strategy (Illustrative) ---
    resistance_level = 82500
    support_level = 82000

    # Calculate trade size based on risk per trade
    risk_points_per_lot = 100
    target_profit_points_per_lot = risk_points_per_lot * RISK_REWARD_RATIO

    risk_per_lot_rupees = risk_points_per_lot * SENSEX_LOT_SIZE

    if risk_per_lot_rupees <= 0:
        logger.error("Calculated risk per lot is zero or negative. Check SENSEX_LOT_SIZE or risk_points_per_lot.")
        return

    num_lots_to_trade = int((total_capital * RISK_PER_TRADE_PERCENT) / risk_per_lot_rupees)
    num_lots_to_trade = max(1, num_lots_to_trade)

    has_open_position = bool(current_positions)
    logger.debug(f"Has open position: {has_open_position}. Lots to trade: {num_lots_to_trade}")

    # Entry Logic
    if not has_open_position:
        if fut_ltp > resistance_level: # Bullish Breakout Signal
            logger.info(f"Bullish breakout detected ({fut_ltp:.2f} > {resistance_level}). Attempting to BUY {num_lots_to_trade} lots.")
            sl_price = fut_ltp - risk_points_per_lot
            tp_price = fut_ltp + target_profit_points_per_lot

            order_id = place_upstox_order(SENSEX_FUT_KEY_ACTIVE, num_lots_to_trade * SENSEX_LOT_SIZE, "BUY", product="NORMAL", price=fut_ltp)
            if order_id:
                logger.info(f"Long Futures Order placed (or simulated). Order ID: {order_id}. SL: {sl_price:.2f}, TP: {tp_price:.2f}")
                # Update current_positions with SL/TP if the order was placed (or simulated)
                if SENSEX_FUT_KEY_ACTIVE in current_positions:
                    current_positions[SENSEX_FUT_KEY_ACTIVE].update({'stop_loss_price': sl_price, 'take_profit_price': tp_price})


        elif fut_ltp < support_level: # Bearish Breakdown Signal
            logger.info(f"Bearish breakdown detected ({fut_ltp:.2f} < {support_level}). Attempting to SELL {num_lots_to_trade} lots.")
            sl_price = fut_ltp + risk_points_per_lot
            tp_price = fut_ltp - target_profit_points_per_lot

            order_id = place_upstox_order(SENSEX_FUT_KEY_ACTIVE, num_lots_to_trade * SENSEX_LOT_SIZE, "SELL", product="NORMAL", price=fut_ltp)
            if order_id:
                logger.info(f"Short Futures Order placed (or simulated). Order ID: {order_id}. SL: {sl_price:.2f}, TP: {tp_price:.2f}")
                # Update current_positions with SL/TP if the order was placed (or simulated)
                if SENSEX_FUT_KEY_ACTIVE in current_positions:
                    current_positions[SENSEX_FUT_KEY_ACTIVE].update({'stop_loss_price': sl_price, 'take_profit_price': tp_price})

    # Position Management (Stop Loss / Take Profit for open positions)
    # Iterate over a copy of keys because the dictionary might be modified during iteration
    positions_to_check = list(current_positions.keys())
    if positions_to_check:
        logger.debug(f"Checking {len(positions_to_check)} open positions for SL/TP.")
    for inst_key in positions_to_check:
        if inst_key == SENSEX_FUT_KEY_ACTIVE and inst_key in current_positions: # Only manage the active future
            pos = current_positions[inst_key]

            # Re-fetch LTP just before checking SL/TP for accuracy
            current_ltp_for_pos = get_ltp(inst_key)
            if current_ltp_for_pos is None:
                logger.warning(f"Could not get current LTP for {inst_key} for SL/TP check. Skipping SL/TP check for this iteration.")
                continue

            logger.debug(f"Position {inst_key}: Side={pos['side']}, Current LTP={current_ltp_for_pos:.2f}, SL={pos['stop_loss_price']:.2f}, TP={pos['take_profit_price']:.2f}")

            if pos['side'] == 'BUY':
                if current_ltp_for_pos <= pos['stop_loss_price']:
                    logger.warning(f"Stop Loss HIT for LONG {inst_key} at {current_ltp_for_pos:.2f}. Closing position.")
                    send_alert_to_mobile(f"Bot: SL HIT for LONG {inst_key} @ {current_ltp_for_pos:.2f}!")
                    place_upstox_order(inst_key, pos['quantity'], "SELL", order_type="MARKET", product="NORMAL")
                    if inst_key in current_positions: # Ensure it still exists before deleting (could be already deleted by another process)
                        logger.debug(f"Removing {inst_key} from local dry run positions after SL hit.")
                        del current_positions[inst_key] # Remove from local tracking
                elif current_ltp_for_pos >= pos['take_profit_price']:
                    logger.info(f"Take Profit HIT for LONG {inst_key} at {current_ltp_for_pos:.2f}. Closing position.")
                    send_alert_to_mobile(f"Bot: TP HIT for LONG {inst_key} @ {current_ltp_for_pos:.2f}!")
                    place_upstox_order(inst_key, pos['quantity'], "SELL", order_type="MARKET", product="NORMAL")
                    if inst_key in current_positions:
                        logger.debug(f"Removing {inst_key} from local dry run positions after TP hit.")
                        del current_positions[inst_key]

            elif pos['side'] == 'SELL':
                if current_ltp_for_pos >= pos['stop_loss_price']:
                    logger.warning(f"Stop Loss HIT for SHORT {inst_key} at {current_ltp_for_pos:.2f}. Closing position.")
                    send_alert_to_mobile(f"Bot: SL HIT for SHORT {inst_key} @ {current_ltp_for_pos:.2f}!")
                    place_upstox_order(inst_key, pos['quantity'], "BUY", order_type="MARKET", product="NORMAL")
                    if inst_key in current_positions:
                        logger.debug(f"Removing {inst_key} from local dry run positions after SL hit.")
                        del current_positions[inst_key]
                elif current_ltp_for_pos <= pos['take_profit_price']:
                    logger.info(f"Take Profit HIT for SHORT {inst_key} at {current_ltp_for_pos:.2f}. Closing position.")
                    send_alert_to_mobile(f"Bot: TP HIT for SHORT {inst_key} @ {current_ltp_for_pos:.2f}!")
                    place_upstox_order(inst_key, pos['quantity'], "BUY", order_type="MARKET", product="NORMAL")
                    if inst_key in current_positions:
                        logger.debug(f"Removing {inst_key} from local dry run positions after TP hit.")
                        del current_positions[inst_key]


                    # --- Main Bot Execution Flow ---
def run_bot_loop():
    """
    Main function to run the Sensex F&O Trading Bot's core logic.
    This function will be run in a separate thread from the Flask UI.
    """
    logger.info("Starting Upstox Sensex F&O Trading Bot...")
    send_alert_to_mobile("Bot: Trading system starting up.")

    load_pnl_history() # Load any previous P&L history

    global total_capital # Declare global to modify the variable
    try:
        # Fetch initial capital and other details for UI
        capital_init_details = get_current_capital_and_pnl_details()
        total_capital = capital_init_details['available_margin'] # Use available margin as effective capital
        bot_status_data["capital_details"] = capital_init_details
        bot_status_data["capital_details"]["initial_capital"] = total_capital # Set initial_capital to current available funds

        if total_capital <= 0:
            logger.critical("No available capital or failed to fetch. Exiting bot.")
            send_alert_to_mobile("Bot CRITICAL: No available capital. Shutting down!")
            bot_status_data["status"] = "Stopped (No Capital)"
            return # Exit run_bot_loop function, but let Flask continue
        logger.info(f"Initial Capital: {total_capital:.2f}")
        send_alert_to_mobile(f"Bot: Initial Capital: INR {total_capital:.2f}")

    except Exception as e:
        logger.critical(f"Failed to initialize capital: {e}", exc_info=True)
        send_alert_to_mobile(f"Bot CRITICAL: Failed to get capital at startup. {e}")
        bot_status_data["status"] = "Stopped (Init Error)"
        return

    # List best strategies to Telegram (one-time call at startup)
    list_best_strategies_to_telegram()

    # Resolve SENSEX_FUT_KEY_ACTIVE once at startup
    current_month_expiry_str = (datetime.now().replace(day=28) + timedelta(days=4)).strftime('%Y%m%d')
    global SENSEX_FUT_KEY_ACTIVE
    SENSEX_FUT_KEY_ACTIVE = get_sensex_instrument_key("FUT", current_month_expiry_str)
    if not SENSEX_FUT_KEY_ACTIVE:
        logger.error("Active Sensex Futures Instrument Key could not be determined at startup. Strategy might not execute.")
        send_alert_to_mobile("Bot Warning: Cannot determine Sensex Futures key. Strategy execution may be affected.")


    # Main trading loop
    try:
        last_graph_minute = -1 # To control graph generation frequency
        while is_market_open():
            current_time = datetime.now()
            bot_status_data["status"] = "Running"
            bot_status_data["last_updated"] = current_time.isoformat()

            # Fetch actual positions from Upstox (or simulated in DRY_RUN_MODE)
            # This also updates `bot_status_data["current_positions_for_ui"]`
            upstox_raw_positions = get_current_positions_from_upstox()

            # Recalculate P&L based on live data and update UI data
            current_fut_ltp = get_ltp(SENSEX_FUT_KEY_ACTIVE)
            if current_fut_ltp is None:
                logger.warning("Could not get Sensex Future LTP for P&L calculation. Skipping current iteration.")
                time.sleep(5) # Pause to prevent rapid error looping
                continue

            current_overall_pnl = calculate_pnl(upstox_raw_positions, current_fut_ltp, None)
            logger.info(f"Current Overall P&L: {current_overall_pnl:.2f}. Daily P&L: {daily_pnl:.2f}")
            update_pnl_history(current_overall_pnl, total_capital)

            # Update overall P&L metrics for UI
            bot_status_data["overall_current_pnl"] = current_overall_pnl
            bot_status_data["overall_daily_pnl"] = daily_pnl

            # Check daily loss limit
            daily_loss_limit_rupees = -(total_capital * MAX_DAILY_LOSS_PERCENT)
            if daily_pnl < daily_loss_limit_rupees:
                logger.critical(f"Daily loss limit ({MAX_DAILY_LOSS_PERCENT*100}%) exceeded (INR {daily_pnl:.2f} < {daily_loss_limit_rupees:.2f}). Shutting down for the day.")
                send_alert_to_mobile(f"Bot CRITICAL: Daily loss limit HIT (INR {daily_pnl:.2f})! Exiting all positions and stopping.")
                close_all_positions() # Close remaining positions
                break # Stop trading for the day

            # Check weekly profit target (needs persistence across days, currently simplified)
            # This would require more sophisticated tracking of cumulative weekly P&L.
            # if current_overall_pnl >= DESIRED_WEEKLY_PROFIT and has_open_position:
            #     logger.info(f"Weekly profit target (INR {DESIRED_WEEKLY_PROFIT}) achieved! Current P&L: {current_overall_pnl:.2f}. Stopping trading for the week.")
            #     send_alert_to_mobile(f"Bot: Weekly profit target ACHIEVED (INR {current_overall_pnl:.2f})! Stopping trading for the week.")
            #     close_all_positions()
            #     break

            execute_sensex_strategy() # Execute your trading strategy

            # Generate graph periodically (e.g., every 30 minutes)
            if current_time.minute % 30 == 0 and current_time.minute != last_graph_minute:
                generate_pnl_graph()
                last_graph_minute = current_time.minute

            time.sleep(10) # Poll every 10 seconds (adjust as needed, consider Upstox rate limits)

        bot_status_data["status"] = "Market Closed"
        logger.info("Market is closed. Bot stopping main trading loop.")
        send_alert_to_mobile("Bot: Market is closed. Stopping trading for the day.")

    except KeyboardInterrupt:
        logger.info("Bot manually stopped via KeyboardInterrupt.")
        send_alert_to_mobile("Bot: Manual shutdown initiated. Attempting to close positions.")
        close_all_positions()
        bot_status_data["status"] = "Stopped (Manual)"
    except Exception as outer_e:
        logger.critical(f"Unhandled critical error in main loop, bot shutting down: {outer_e}", exc_info=True)
        send_alert_to_mobile(f"Bot CRITICAL: Unhandled error, shutting down! {outer_e}")
        close_all_positions()
        bot_status_data["status"] = "Stopped (Error)"
        sys.exit(1) # Exit with an error code

    finally:
        logger.info("Upstox Sensex F&O Trading Bot gracefully stopped.")
        send_alert_to_mobile("Bot: Trading system stopped.")
        generate_pnl_graph() # Generate final graph on exit
        save_pnl_history() # Ensure P&L history is saved on exit

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/status')
def status():
    # Return current bot status and data as JSON
    return jsonify(bot_status_data)


def is_market_open():
    """Checks if the Indian F&O market is currently open based on IST."""
    now = datetime.now()
    market_start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end_time = now.replace(hour=15, minute=30, second=0, microsecond=0)

    # Check for weekends (Saturday=5, Sunday=6)
    if now.weekday() >= 5:
        logger.info("Market closed: Weekend.")
        return False

    # Check for market holidays (Requires fetching and checking a list of holidays)
    # Example: if check_for_holiday(now.date()): return False

    # Check if current time is within market hours
    if not (market_start_time <= now <= market_end_time):
        logger.info(f"Market closed: Outside trading hours. Current time: {now.strftime('%H:%M:%S')}")
        return False

    return True

# --- Main execution point ---
if __name__ == "__main__":
    # Validate API credentials at startup
    if not API_KEY or not API_SECRET or not ACCESS_TOKEN:
        logger.error("API_KEY, API_SECRET, or ACCESS_TOKEN not configured. Please set them.")
        logger.error("Refer to Upstox API documentation for authentication setup.")
        sys.exit(1)

    # Warn if Telegram credentials are not set
    if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN" or TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_CHAT_ID":
        logger.warning("Telegram bot credentials are not set or are placeholders. Alerts will not be sent.")

    # Start the trading bot logic in a separate thread
    # This allows the Flask app to run independently and serve requests.
    trading_bot_thread = threading.Thread(target=run_bot_loop)
    trading_bot_thread.daemon = True # Allow the main program to exit even if this thread is running
    trading_bot_thread.start()

    # Start the Flask UI server
    # Running on 0.0.0.0 makes it accessible from other devices on the same network
    # debug=True allows for auto-reloading and better error messages during development.
    logger.info("Starting Flask UI server on http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False) # use_reloader=False when using threads
