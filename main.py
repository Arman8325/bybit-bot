        # --- Прогноз на следующие 15 минут ---
        forecast = "NEUTRAL"
        forecast_reasons = []

        if adx > 20:
            if momentum > 0 and rsi > 55 and cci > 50 and last_close > ema:
                forecast = "LONG"
                forecast_reasons.append("цена выше EMA и индикаторы в бычьей зоне")
            elif momentum < 0 and rsi < 45 and cci < -50 and last_close < ema:
                forecast = "SHORT"
                forecast_reasons.append("цена ниже EMA и индикаторы в медвежьей зоне")
        else:
            forecast = "NEUTRAL"
            forecast_reasons.append("ADX < 20 (слабый тренд)")

        bot.send_message(message.chat.id, f"""
📈 Закрытие: {last_close}
📉 Предыдущая: {prev_close}
📊 RSI: {round(rsi, 2)}
📈 EMA21: {round(ema, 2)}
📊 ADX: {round(adx, 2)}
📊 CCI: {round(cci, 2)}
📊 Stochastic: {round(stoch, 2)}
📊 Momentum: {round(momentum, 2)}
📊 Bollinger Mid: {round(bb.bollinger_mavg().iloc[-1], 2)}
📌 Сигнал: {signal}
🔮 Прогноз на следующие 15 минут: {forecast}
ℹ️ Причина прогноза: {', '.join(forecast_reasons)}
        """)
