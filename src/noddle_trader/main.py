# main.py
import pandas as pd
from datetime import datetime, timedelta
import time
import json

# Asegúrate de que la importación usa la nueva clase de data_feed
from .data_feed import data_feed # Importar la instancia global
from .strategy import ICTMSSStrategy
import MetaTrader5 as mt5


def cargar_configuracion():
    """Cargar configuración de la estrategia mejorada."""
    return {
        # --- Parámetros de Riesgo ---
        "CUENTA_INICIAL": 10000,
        "RIESGO_POR_OPERACION": 0.1,    # 1% de riesgo por operación (más conservador)
        "RR": 1.5,                       # Risk/Reward 1:2
        "VALOR_POR_PIP": 10,             # USD por pip (lote estándar para EURUSD)
        
        # --- Parámetros de Análisis ---
        "SYMBOL": "EURUSD",
        "VELAS_M15": 15,                 # Analizar el M15 de las últimas 7.5 horas
        "VELAS_M1": 7,                  # Ventana en M1 para buscar FVG
        "USAR_FILTRO_SESION": False,      # True para operar solo en sesión NY, False para operar 24h
        
        # --- Parámetros de Ejecución ---
        "INTERVALO_ANALISIS": 5,        # Chequeo cada 5 segundos
    }


def obtener_datos_estrategia(symbol, velas_m15, velas_m1):
    """
    Obtener datos históricos necesarios para la estrategia usando el nuevo data_feed.

    Args:
        symbol: Símbolo a analizar
        velas_m15: Número de velas M15 a obtener
        velas_m1: Número de velas M1 a obtener

    Returns:
        Tuple con (df_m15, df_m1)
    """
    df_m15 = data_feed.obtener_datos_por_velas(symbol, "M15", velas_m15)
    df_m1 = data_feed.obtener_datos_por_velas(symbol, "M1", velas_m1)
    
    # Validar datos
    if not data_feed.validar_datos(df_m15) or not data_feed.validar_datos(df_m1):
        print("❌ Datos inválidos detectados.")
        return pd.DataFrame(), pd.DataFrame()

    return df_m15, df_m1


def mostrar_señal(señal):
    """Mostrar información de la señal generada"""
    print("\n" + "=" * 50)
    print("🚨 SEÑAL FVG DETECTADA (ESTRATEGIA MEJORADA)")
    print("=" * 50)
    print(f"📊 Dirección: {señal['direccion'].upper()}")
    print(f"💰 Precio entrada: {señal['precio_entrada']:.5f}")
    print(f"🛑 Stop Loss: {señal['stop_loss']:.5f}")
    print(f"🎯 Take Profit: {señal['take_profit']:.5f}")
    print(f"📏 Distancia SL: {señal['distancia_sl']*10000:.1f} pips")
    print(f"📊 RR Ratio: 1:{señal['rr_ratio']}")
    print(f"💼 Tamaño lote: {señal['tamaño_lote']}")
    print(f"⏰ Timestamp: {señal['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)


def mostrar_estadisticas(estrategia):
    """Mostrar estadísticas de rendimiento"""
    stats = estrategia.obtener_estadisticas()

    print("\n" + "=" * 40)
    print("📈 ESTADÍSTICAS DE RENDIMIENTO")
    print("=" * 40)
    print(f"Total operaciones: {stats['total_operaciones']}")

    if stats["total_operaciones"] > 0:
        print(f"Ganadas: {stats['ganadas']}")
        print(f"Perdidas: {stats['perdidas']}")
        print(f"Win Rate: {stats['win_rate']:.1f}%")
        print(f"Profit Factor: {stats['profit_factor']:.2f}")
    print("=" * 40)


def modo_tiempo_real(estrategia, config):
    """Ejecutar estrategia en tiempo real"""
    print("🔴 Iniciando análisis en tiempo real (Estrategia Mejorada)...")
    print(f"📊 Símbolo: {config['SYMBOL']}")
    print(f"⏰ Intervalo: {config['INTERVALO_ANALISIS']} segundos")
    print(f"⏳ Filtro de Sesión NY: {'Activado' if config['USAR_FILTRO_SESION'] else 'Desactivado'}")
    print("Presiona Ctrl+C para detener\n")

    try:
        while True:
            print(f"🔍 Analizando mercado... {datetime.now().strftime('%H:%M:%S')}", end="\r")

            # Obtener datos actuales
            df_m15, df_m1 = obtener_datos_estrategia(
                config["SYMBOL"], config["VELAS_M15"], config["VELAS_M1"]
            )

            if not df_m15.empty and not df_m1.empty:
                señal = estrategia.analizar_mercado(df_m15, df_m1)

                if señal:
                    mostrar_señal(señal)
                    print("⚠️  MODO DEMO: No se ejecuta operación real. Registrando para estadísticas.")
                    estrategia.registrar_operacion({"resultado": "pendiente", **señal}) # Simulación
                    time.sleep(60) # Pausa después de señal para no operar la misma vela
                
            # Esperar próximo análisis
            time.sleep(config["INTERVALO_ANALISIS"])

    except KeyboardInterrupt:
        print("\n🛑 Deteniendo análisis...")
        mostrar_estadisticas(estrategia)

# --- No es necesario modificar modo_backtest ni la función main, pero sí ---
# --- asegurarse de que las llamadas a obtener_datos usan los nuevos métodos ---

def main():
    """Función principal"""
    # La instancia global de data_feed ya se conecta en data_feed.py
    if not data_feed.is_connected():
        print("❌ Error al conectar con MetaTrader 5. Revisa data_feed.py")
        return
        
    try:
        config = cargar_configuracion()
        estrategia = ICTMSSStrategy(config)

        print("🤖 NODDLE TRADER - Estrategia ICT FVG (Mejorada)")
        print("=" * 40)
        # Simplificado para enfocarse en el modo en tiempo real que es donde se probará la nueva lógica.
        modo_tiempo_real(estrategia, config)

    finally:
        estrategia.generar_reporte_analisis()
        print("🔄 Generando reporte de análisis...")
        data_feed.disconnect()
        print("✅ Conexión MT5 cerrada")


if __name__ == "__main__":
    main()