# Author: Sandeep Belgavi
# Date:   2025-05-02

import matplotlib
matplotlib.use('Agg')

from flask import Flask, request, jsonify, render_template
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
import base64

app = Flask(__name__)


def fetch_data(symbol, period='1y'):
    data = yf.download(symbol, period=period, auto_adjust=False, progress=False)
    if data.empty:
        return None
    return data

def calculate_indicators(df, algorithms):
    results = {}
    if 'sma' in algorithms:
        df['SMA_20'] = df['Close'].rolling(window=20, min_periods=1).mean()
        results['sma'] = True
    if 'ema' in algorithms:
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        results['ema'] = True
    if 'rsi' in algorithms:
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        results['rsi'] = True
    if 'macd' in algorithms:
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = ema12 - ema26
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        results['macd'] = True
    if 'bollinger' in algorithms:
        ma20 = df['Close'].rolling(window=20).mean()
        std20 = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = ma20 + 2 * std20
        df['BB_Lower'] = ma20 - 2 * std20
        results['bollinger'] = True
    if 'supertrend' in algorithms:
        period = 10
        multiplier = 3
        high = df['High']
        low = df['Low']
        close = df['Close']
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()
        hl2 = (high + low) / 2
        upperband = hl2 + (multiplier * atr)
        lowerband = hl2 - (multiplier * atr)
        supertrend = [True] * len(df)
        for i in range(1, len(df)):
            if close.iloc[i] > upperband.iloc[i-1]:
                supertrend[i] = True
            elif close.iloc[i] < lowerband.iloc[i-1]:
                supertrend[i] = False
            else:
                supertrend[i] = supertrend[i-1]
                if supertrend[i] and lowerband.iloc[i] < lowerband.iloc[i-1]:
                    lowerband.iloc[i] = lowerband.iloc[i-1]
                if not supertrend[i] and upperband.iloc[i] > upperband.iloc[i-1]:
                    upperband.iloc[i] = upperband.iloc[i-1]
        st = pd.Series(index=df.index, dtype=float)
        for i in range(len(df)):
            st.iloc[i] = lowerband.iloc[i] if supertrend[i] else upperband.iloc[i]
        df['Supertrend'] = st
        df['Supertrend_Signal'] = [1 if x else -1 for x in supertrend]
        results['supertrend'] = True
    if 'adx' in algorithms:
        high = df['High']
        low = df['Low']
        close = df['Close']
        plus_dm = high.diff()
        minus_dm = low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0
        tr1 = pd.DataFrame({'tr0': high - low, 'tr1': (high - close.shift()).abs(), 'tr2': (low - close.shift()).abs()}).max(axis=1)
        atr = tr1.rolling(window=14).mean()
        plus_di = 100 * (plus_dm.rolling(window=14).mean() / atr)
        minus_di = abs(100 * (minus_dm.rolling(window=14).mean() / atr))
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        df['ADX'] = dx.rolling(window=14).mean()
        results['adx'] = True
    if 'stochastic' in algorithms:
        low_min = df['Low'].rolling(window=14).min()
        high_max = df['High'].rolling(window=14).max()
        df['Stochastic_K'] = 100 * (df['Close'] - low_min) / (high_max - low_min)
        df['Stochastic_D'] = df['Stochastic_K'].rolling(window=3).mean()
        results['stochastic'] = True
    if 'cci' in algorithms:
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        ma = tp.rolling(window=20).mean()
        md = tp.rolling(window=20).apply(lambda x: np.mean(np.abs(x - np.mean(x))))
        df['CCI'] = (tp - ma) / (0.015 * md)
        results['cci'] = True
    if 'obv' in algorithms:
        obv = [0]
        for i in range(1, len(df)):
            if df['Close'][i] > df['Close'][i-1]:
                obv.append(obv[-1] + df['Volume'][i])
            elif df['Close'][i] < df['Close'][i-1]:
                obv.append(obv[-1] - df['Volume'][i])
            else:
                obv.append(obv[-1])
        df['OBV'] = obv
        results['obv'] = True
    return df, results

def generate_plot_base64(df, symbol, algorithms):
    plt.figure(figsize=(14, 7))
    plt.plot(df['Close'], label='Close', alpha=0.7)
    if 'sma' in algorithms and 'SMA_20' in df:
        plt.plot(df['SMA_20'], label='SMA 20', linestyle='--')
    if 'ema' in algorithms and 'EMA_20' in df:
        plt.plot(df['EMA_20'], label='EMA 20', linestyle='--')
    if 'bollinger' in algorithms and 'BB_Upper' in df and 'BB_Lower' in df:
        plt.plot(df['BB_Upper'], label='Bollinger Upper', linestyle=':', color='green')
        plt.plot(df['BB_Lower'], label='Bollinger Lower', linestyle=':', color='red')
    if 'supertrend' in algorithms and 'Supertrend' in df:
        plt.plot(df['Supertrend'], label='Supertrend', color='purple', linewidth=1.5)
    if 'macd' in algorithms and 'MACD' in df and 'MACD_Signal' in df:
        plt.plot(df['MACD'], label='MACD', color='orange')
        plt.plot(df['MACD_Signal'], label='MACD Signal', color='brown')
    if 'adx' in algorithms and 'ADX' in df:
        plt.plot(df['ADX'], label='ADX', color='teal')
    if 'stochastic' in algorithms and 'Stochastic_K' in df and 'Stochastic_D' in df:
        plt.plot(df['Stochastic_K'], label='Stochastic %K', color='magenta')
        plt.plot(df['Stochastic_D'], label='Stochastic %D', color='cyan')
    if 'cci' in algorithms and 'CCI' in df:
        plt.plot(df['CCI'], label='CCI', color='grey')
    if 'obv' in algorithms and 'OBV' in df:
        plt.plot(df['OBV'], label='OBV', color='black')
    if 'rsi' in algorithms and 'RSI' in df:
        plt.plot(df['RSI'], label='RSI', color='pink')
    plt.title(f"{symbol} Historical Trend with Selected Algorithms")
    plt.xlabel('Date')
    plt.ylabel('Price/Indicator')
    plt.legend()
    plt.grid(True)
    buffer = BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight')
    plt.close()
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode('utf-8')

def generate_signals_data(df, algorithms):
    signals = []
    if 'supertrend' in algorithms and 'Supertrend_Signal' in df:
        st_sig = df['Supertrend_Signal'].values
        for i in range(1, len(df)):
            if st_sig[i-1] == -1 and st_sig[i] == 1:
                signals.append({'date': df.index[i].strftime('%Y-%m-%d'), 'type': 'Buy'})
            elif st_sig[i-1] == 1 and st_sig[i] == -1:
                signals.append({'date': df.index[i].strftime('%Y-%m-%d'), 'type': 'Sell'})
    # You can add more signal logic for other indicators here
    return signals

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze')
def analyze():
    symbol = request.args.get('symbol')
    algorithms = request.args.get('algorithms', '').split(',')
    if not symbol:
        return jsonify({'error': 'Please provide a symbol.'})
    data = fetch_data(symbol)
    if data is None:
        return jsonify({'error': f'No data found for symbol: {symbol}'})
    data, _ = calculate_indicators(data, algorithms)
    plot_data = generate_plot_base64(data, symbol, algorithms)
    signals = generate_signals_data(data, algorithms)
    return jsonify({'plot_data': plot_data, 'signals': signals})

if __name__ == '__main__':
    app.run(debug=True)
