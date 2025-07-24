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
price = exchange.fetch_ticker(symbol)['last']
timeframe = '5m'
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

        usdt_balance = balance.get('USDT', {}).get('free', 0.0)
        sol_balance = balance.get('SOL', {}).get('free', 0.0)
        return {
            'USDT': usdt_balance,
            'SOL': sol_balance
        }
    except Exception as e:
        print(f"❌ Erro ao verificar saldo: {e}")
        return None

def fetch_market_data():
    try:
        sync_time()
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        close_prices = np.array([x[4] for x in ohlcv], dtype=np.float64)
        volumes = np.array([x[5] for x in ohlcv], dtype=np.float64)
        
        # Verifica dados suficientes
        if len(close_prices) < 50:
            raise ValueError("Dados insuficientes para análise")
            
        return close_prices, volumes
    except Exception as e:
        print(f"❌ Erro ao obter dados: {e}")
        return None

def calculate_indicators(prices, volumes):
    try:
        # MACD
        macd, signal, _ = talib.MACD(prices, 12, 26, 9)
        
        # RSI com limites
        rsi = np.clip(talib.RSI(prices, 14), 1, 99)
        
        # Stoch RSI otimizado
        fastk, fastd = talib.STOCHRSI(
            prices,
            timeperiod=14,      
            fastk_period=14,    
            fastd_period=3,     
            fastd_matype=3      
        )
        valid_k = fastk[~np.isnan(fastk)]
        stoch_rsi = valid_k[-1]
                
        # Volume e Volume MA (10 períodos)
        current_volume = volumes[-1]
        volume_ma_10 = talib.SMA(volumes, timeperiod=10)[-1]
        
        # EMA (9 períodos)
        ema_9 = talib.EMA(prices, timeperiod=9)[-1]

        return {
            'macd': macd[-1],
            'signal': signal[-1],
            'histogram': (macd - signal)[-1],
            'rsi': rsi[-1],
            'stoch_rsi': stoch_rsi,
            'volume': current_volume,
            'volume_ma_10': volume_ma_10,
            'ema_9': ema_9
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

    prices, volumes = fetch_market_data()
    if prices is None:
        return
    if volumes is None:
        return

    indicators = calculate_indicators(prices, volumes)
    if not indicators:
        return

    min_histogram = price * 0.0005
    # min_histogram = 0.001

    timestamp = time.time()

    # Converte para struct_time (formato local)
    tempo_local = time.localtime(timestamp)

    # Formata para HH:MM
    hora_formatada = time.strftime("%H:%M", tempo_local)

    print(f"\n⏰ Timestamp: {hora_formatada}")
    print(f"📊 Análise:")
    print(f"MACD: {indicators['macd']:.2f} | Signal: {indicators['signal']:.4f}")
    print(f"Histograma: {indicators['histogram']:.4f} | RSI: {indicators['rsi']:.1f}")
    print(f"MinHistograma: {min_histogram:.4f}")
    print(f"StochRSI: {indicators['stoch_rsi']:.1f} | EMA9: {indicators['ema_9']:.4f}")
    print(f"VolumeMA10: {indicators['volume_ma_10']:.1f} | Volume: {indicators['volume']:.4f}")
    print(f"💰 Saldo: USDT={balance['USDT']:.2f} | SOL={balance['SOL']:.4f}\n")

    

    # Lógica de negociação
    if (indicators['macd'] > indicators['signal'] and 
        indicators['macd'] > 0 and  
        indicators['histogram'] > min_histogram and
        indicators['stoch_rsi'] < 80 and                    
        indicators['rsi'] < 65 and 
        indicators['volume'] > indicators['volume_ma_10'] and
        price > indicators['ema_9'] and    
        total_buys < limit_buys and
        balance['USDT'] > 10):
        
        amount = min(0.5, balance['USDT'] / prices[-1])
        if amount >= min_order_amount:
            print("🚀 Sinal de COMPRA detectado!")
            buy(symbol, round(amount, 2))
            total_buys += 1
        else:
            print("⚠️ Saldo insuficiente para compra mínima")

    elif (indicators['stoch_rsi'] > 85 or             # Sobrecompra extrema
        indicators['rsi'] > 70 or                     # RSI alto
        indicators['macd'] < indicators['signal'] or  # Cruzamento de baixa
        price < indicators['ema_9']                   # Perda de momentum
        ) and balance['SOL'] > 0:
        
        if indicators['stoch_rsi'] > 90:
            print("🎯 Sinal de VENDA IDEAL!")
            sell(symbol, round(balance['SOL'], 4))
            total_buys = 0
        elif indicators['stoch_rsi'] > 85:
            print("📉 Sinal de VENDA PARCIAL")
            sell(symbol, round(balance['SOL'] * 0.3, 4))
            total_buys = max(0, total_buys - 1)

# Agendamento
def get_next_candle_close_time():
    now = int(time.time() * 1000) 
    candle_duration = 5 * 60 * 1000
    return ((now // candle_duration) + 1) * candle_duration

def run_at_candle_close():
    next_close = get_next_candle_close_time()
    sleep_time = (next_close - int(time.time() * 1000)) / 1000
    if sleep_time > 0:
        time.sleep(sleep_time)
    execute_strategy()

if __name__ == "__main__":
    print("🤖 Bot iniciado - Binance Testnet")
    # execute_strategy()
    while True:
        try:
            run_at_candle_close()
            time.sleep(0.1)
        except KeyboardInterrupt:
            print("🛑 Bot interrompido")
            break
        except Exception as e:
            print(f"⚠️ Erro no loop principal: {e}")
            time.sleep(5)