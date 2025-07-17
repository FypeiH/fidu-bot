import ccxt
import talib
import numpy as np
import schedule
import time
from decouple import config
from datetime import datetime

# Initialize Binance API connection
exchange = ccxt.binance({
    'apiKey': config('BINANCE_API_KEY'),
    'secret': config('BINANCE_SECRET_KEY'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
        'adjustForTimeDifference': True,
    },
})

exchange.set_sandbox_mode(True)  # Use testnet for Binance

# Configurações globais
symbol = 'SOL/USDT'
timeframe = '1h'
total_buys = 0
limit_buys = 3
min_order_amount = 0.1  # Quantidade mínima para ordens

def sync_time():
    try:
        server_time = exchange.fetch_time()
        local_time = int(time.time() * 1000)
        exchange.time_difference = server_time - local_time
        if abs(exchange.time_difference) > 1000:
            print(f"⏰ Ajustado diferença temporal: {exchange.time_difference}ms")
    except Exception as e:
        print(f"⚠️ Falha na sincronização: {e}")

def check_balance():
    try:
        sync_time()
        balance = exchange.fetch_balance()
        return {
            'USDT': balance['USDT']['free'],
            'SOL': balance['SOL']['free']
        }
    except Exception as e:
        print(f"❌ Erro ao verificar saldo: {e}")
        return None

def fetch_market_data():
    try:
        sync_time()
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        close_prices = np.array([x[4] for x in ohlcv], dtype=np.float64)
        
        # Verifica dados suficientes
        if len(close_prices) < 50:
            raise ValueError("Dados insuficientes para análise")
            
        return close_prices
    except Exception as e:
        print(f"❌ Erro ao obter dados: {e}")
        return None

def calculate_indicators(prices):
    try:
        # MACD
        macd, signal, _ = talib.MACD(prices, 12, 26, 9)
        
        # RSI com limites
        rsi = np.clip(talib.RSI(prices, 14), 5, 95)
        
        # Stoch RSI otimizado
        fastk, _ = talib.STOCHRSI(prices, 21, 14, 3)
        valid_stoch = fastk[~np.isnan(fastk)]
        stoch_rsi = np.clip(valid_stoch[-1] if len(valid_stoch) > 0 else 50, 5, 95)
        
        return {
            'macd': macd[-1],
            'rsi': rsi[-1],
            'stoch_rsi': stoch_rsi
        }
    except Exception as e:
        print(f"⚠️ Erro nos cálculos: {e}")
        return None
    
def buy(symbol, amount):
    try:
        order = exchange.create_market_buy_order(symbol, amount)
        print(f"✅ Compra executada: {order}")
    except Exception as e:
        print(f"❌ Erro ao comprar: {e}")

def sell(symbol, amount):
    try:
        order = exchange.create_market_sell_order(symbol, amount)
        print(f"✅ Venda executada: {order}")
    except Exception as e:
        print(f"❌ Erro ao vender: {e}")

def execute_strategy():
    global total_buys
    
    # Verificação inicial
    balance = check_balance()
    if not balance:
        return

    prices = fetch_market_data()
    if prices is None:
        return

    indicators = calculate_indicators(prices)
    if not indicators:
        return

    print(f"\n📊 Análise: MACD={indicators['macd']:.2f} | RSI={indicators['rsi']:.2f} | StochRSI={indicators['stoch_rsi']:.2f}")
    print(f"💰 Saldo: USDT={balance['USDT']:.2f} | SOL={balance['SOL']:.4f}")

    # Lógica de negociação
    if (indicators['macd'] < 0 
        and indicators['rsi'] < 30 
        and indicators['stoch_rsi'] < 20 
        and total_buys < limit_buys
        and balance['USDT'] > 10):  # Pelo menos 10 USDT
        
        amount = min(0.5, balance['USDT'] / prices[-1])  # Calcula quantidade
        if amount >= min_order_amount:
            print("🚀 Sinal de COMPRA detectado!")
            buy(symbol, round(amount, 2))
            total_buys += 1
        else:
            print("⚠️ Saldo insuficiente para compra mínima")

    elif (indicators['macd'] > 0.5 
          and indicators['rsi'] > 65 
          and balance['SOL'] > 0):
        
        if indicators['stoch_rsi'] > 90:
            print("🎯 Sinal de VENDA IDEAL!")
            sell(symbol, round(balance['SOL'], 4))
            total_buys = 0
        elif indicators['stoch_rsi'] > 85:
            print("📉 Sinal de VENDA PARCIAL")
            sell(symbol, round(balance['SOL'] / 3, 4))
            total_buys = max(0, total_buys - 1)

# Agendamento
schedule.every(5).minutes.do(execute_strategy)

if __name__ == "__main__":
    print("🤖 Bot iniciado - Binance Testnet")
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            print("🛑 Bot interrompido")
            break
        except Exception as e:
            print(f"⚠️ Erro no loop principal: {e}")
            time.sleep(5)